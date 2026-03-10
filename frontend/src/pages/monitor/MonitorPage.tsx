import {
  AlertOutlined,
  DashboardOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  WarningOutlined
} from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  Progress,
  Row,
  Space,
  Statistic,
  Tag,
  Tooltip,
  Typography,
  message
} from "antd";
import { fetchQueueStats, moveDeadJobs } from "../../shared/api/modules/monitor";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { ConfirmAction } from "../../shared/components/ConfirmAction";
import { CompactPageHero } from "../../shared/components/CompactPageHero";
import {
  DonutMetricChart,
  MetricBarChart,
  MiniTrendChart,
  TrendDatum
} from "../../shared/components/MetricCharts";
import { PageState } from "../../shared/components/PageState";

const METRIC_ITEMS = [
  { key: "queued", label: "排队中", color: "#94a3b8" },
  { key: "started", label: "执行中", color: "#2563eb" },
  { key: "deferred", label: "延迟中", color: "#f59e0b" },
  { key: "finished", label: "已完成", color: "#16a34a" },
  { key: "failed_registry", label: "失败登记", color: "#dc2626" },
  { key: "dead", label: "死信队列", color: "#7c3aed" },
  { key: "scheduled", label: "已调度", color: "#0ea5a0" }
] as const;

const SNAPSHOT_LIMIT = 8;

function resolveHealthTag(riskPercent: number) {
  if (riskPercent > 35) {
    return (
      <Tag color="error" icon={<WarningOutlined />}>
        高风险
      </Tag>
    );
  }
  if (riskPercent > 15) {
    return (
      <Tag color="warning" icon={<AlertOutlined />}>
        中风险
      </Tag>
    );
  }
  return (
    <Tag color="success" icon={<SafetyCertificateOutlined />}>
      低风险
    </Tag>
  );
}

function formatSnapshotLabel(index: number) {
  return `T${index + 1}`;
}

export function MonitorPage() {
  const [lastMoveRequestId, setLastMoveRequestId] = useState<string | null>(null);
  const [queueSnapshots, setQueueSnapshots] = useState<TrendDatum[]>([]);
  const [riskSnapshots, setRiskSnapshots] = useState<TrendDatum[]>([]);

  const statsQuery = useQuery({
    queryKey: ["monitor", "queues"],
    queryFn: fetchQueueStats,
    refetchInterval: 10_000
  });

  const moveMutation = useMutation({
    mutationFn: moveDeadJobs,
    onSuccess: (data) => {
      setLastMoveRequestId(data.request_id ?? null);
      message.success(`已迁移 ${data.moved} 条失败任务`);
      void statsQuery.refetch();
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const stats = statsQuery.data?.stats;
  const alerts = statsQuery.data?.alerts ?? [];
  const normalizedError = statsQuery.isError ? normalizeApiError(statsQuery.error) : null;

  const totalInQueue = stats
    ? stats.queued +
      stats.started +
      stats.deferred +
      stats.finished +
      stats.failed_registry +
      stats.dead +
      stats.scheduled
    : 0;

  const riskPercent = totalInQueue
    ? Math.min(
        100,
        Math.round((((stats?.failed_registry ?? 0) + (stats?.dead ?? 0)) / totalInQueue) * 100)
      )
    : 0;

  useEffect(() => {
    if (!statsQuery.data) {
      return;
    }

    setQueueSnapshots((previous) => {
      const next = [...previous, { key: `queue-${previous.length + 1}`, label: "", value: totalInQueue }]
        .slice(-SNAPSHOT_LIMIT)
        .map((item, index) => ({
          ...item,
          key: `queue-${index + 1}`,
          label: formatSnapshotLabel(index)
        }));
      return next;
    });

    setRiskSnapshots((previous) => {
      const next = [...previous, { key: `risk-${previous.length + 1}`, label: "", value: riskPercent }]
        .slice(-SNAPSHOT_LIMIT)
        .map((item, index) => ({
          ...item,
          key: `risk-${index + 1}`,
          label: formatSnapshotLabel(index)
        }));
      return next;
    });
  }, [riskPercent, statsQuery.data, totalInQueue]);

  const hasAnyStats = Boolean(totalInQueue || alerts.length);
  const pageStatus = statsQuery.isLoading
    ? "loading"
    : statsQuery.isError
      ? "error"
      : hasAnyStats
        ? "success"
        : "empty";

  const chartItems = useMemo(
    () =>
      METRIC_ITEMS.map((item) => ({
        key: item.key,
        label: item.label,
        value: stats?.[item.key] ?? 0,
        color: item.color
      })),
    [stats]
  );

  return (
    <PageState
      status={pageStatus}
      errorTitle={normalizedError?.message}
      errorSubTitle={
        normalizedError
          ? `${normalizedError.code}${
              normalizedError.request_id ? `，request_id=${normalizedError.request_id}` : ""
            }`
          : undefined
      }
    >
      <div className="page-stack">
        <CompactPageHero
          kicker="队列监控"
          title="队列监控中心"
          description="实时查看入库队列压力、失败任务和死信风险，帮助管理端快速判断是否需要人工介入。"
          stats={[
            { label: "总量", value: totalInQueue },
            { label: "执行中", value: stats?.started ?? 0 },
            { label: "失败", value: stats?.failed_registry ?? 0 },
            { label: "风险", value: `${riskPercent}%` }
          ]}
        />

        <div className="dashboard-grid">
          <Card className="card-soft" size="small" title="队列结构">
            <DonutMetricChart
              items={chartItems}
              centerLabel="任务总量"
              centerValue={totalInQueue}
              emptyText="暂无队列结构数据"
            />
          </Card>
          <Card className="card-soft" size="small" title="阶段对比">
            <MetricBarChart items={chartItems} emptyText="暂无阶段分布数据" />
          </Card>
        </div>

        <div className="dashboard-grid">
          <Card className="card-soft" size="small" title="总量趋势">
            <MiniTrendChart
              items={queueSnapshots}
              stroke="#2563eb"
              emptyText="等待队列趋势数据"
            />
          </Card>
          <Card className="card-soft" size="small" title="风险趋势">
            <MiniTrendChart
              items={riskSnapshots}
              stroke="#dc2626"
              emptyText="等待风险趋势数据"
              valueFormatter={(value) => `${value}%`}
            />
          </Card>
        </div>

        <Card
          title={
            <Space size={8}>
              <DashboardOutlined />
              <span>队列总览</span>
            </Space>
          }
          className="card-soft"
          extra={
            <Space size={8}>
              <Tag bordered={false} color="blue">
                10s
              </Tag>
              <Tooltip title="刷新队列统计">
                <Button
                  size="small"
                  shape="circle"
                  icon={<ReloadOutlined />}
                  onClick={() => void statsQuery.refetch()}
                  loading={statsQuery.isFetching}
                  aria-label="刷新队列统计"
                />
              </Tooltip>
              <Tooltip title="迁移失败任务到死信队列">
                <span>
                  <ConfirmAction
                    title="确认迁移失败任务到死信队列？"
                    description="该操作会批量迁移失败任务，建议先核对当前告警和任务状态。"
                    okText="确认迁移"
                    cancelText="返回"
                    onConfirm={() => {
                      moveMutation.mutate();
                    }}
                    buttonText=""
                    danger
                    size="small"
                    shape="circle"
                    icon={<WarningOutlined />}
                    loading={moveMutation.isPending}
                    ariaLabel="迁移失败任务到死信队列"
                  />
                </span>
              </Tooltip>
            </Space>
          }
        >
          <Space direction="vertical" size={18} style={{ width: "100%" }}>
            <div className="monitor-health-row">
              <Space size={10} wrap>
                <Typography.Text type="secondary">当前健康度</Typography.Text>
                {resolveHealthTag(riskPercent)}
              </Space>
              <Typography.Text type="secondary">
                {lastMoveRequestId ? "最近一次死信迁移已完成" : "暂无死信迁移动作"}
              </Typography.Text>
            </div>
            <Progress
              percent={riskPercent}
              strokeColor={
                riskPercent > 35 ? "#cf3f3f" : riskPercent > 15 ? "#e5a100" : "#0ea5a0"
              }
              format={(percent) => `风险 ${percent}%`}
            />
            <Row gutter={[16, 16]}>
              {METRIC_ITEMS.map((item) => (
                <Col key={item.key} xs={12} md={8} lg={6}>
                  <Card size="small" className="monitor-metric-card">
                    <Statistic
                      title={item.label}
                      value={stats?.[item.key] ?? 0}
                      valueStyle={{ color: item.key === "dead" ? "#cf3f3f" : undefined }}
                    />
                  </Card>
                </Col>
              ))}
            </Row>
          </Space>
        </Card>

        <Card
          title={
            <Space size={8}>
              <AlertOutlined />
              <span>告警列表</span>
            </Space>
          }
          className="card-soft"
        >
          {alerts.length ? (
            <div className="monitor-alert-list">
              {alerts.map((item) => (
                <Alert key={item} type="warning" showIcon message={item} />
              ))}
            </div>
          ) : (
            <Alert type="success" showIcon message="暂无告警" />
          )}
        </Card>
      </div>
    </PageState>
  );
}
