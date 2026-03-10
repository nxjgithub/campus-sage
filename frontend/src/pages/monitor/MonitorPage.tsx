import {
  AlertOutlined,
  DashboardOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  WarningOutlined
} from "@ant-design/icons";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Col, Progress, Row, Space, Statistic, Tag, Typography, message } from "antd";
import { fetchQueueStats, moveDeadJobs } from "../../shared/api/modules/monitor";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { ConfirmAction } from "../../shared/components/ConfirmAction";
import { PageState } from "../../shared/components/PageState";

const METRIC_ITEMS = [
  { key: "queued", label: "排队中" },
  { key: "started", label: "执行中" },
  { key: "deferred", label: "延迟中" },
  { key: "finished", label: "已完成" },
  { key: "failed_registry", label: "失败注册" },
  { key: "dead", label: "死信队列" },
  { key: "scheduled", label: "已调度" }
] as const;

export function MonitorPage() {
  const [lastMoveRequestId, setLastMoveRequestId] = useState<string | null>(null);

  const statsQuery = useQuery({
    queryKey: ["monitor", "queues"],
    queryFn: fetchQueueStats,
    refetchInterval: 10_000
  });

  const moveMutation = useMutation({
    mutationFn: moveDeadJobs,
    onSuccess: (data) => {
      setLastMoveRequestId(data.request_id ?? null);
      message.success(`已转移 ${data.moved} 条任务`);
      void statsQuery.refetch();
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const stats = statsQuery.data?.stats;
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
  const hasAnyStats = Boolean(totalInQueue || statsQuery.data?.alerts.length);
  const pageStatus = statsQuery.isLoading
    ? "loading"
    : statsQuery.isError
      ? "error"
      : hasAnyStats
        ? "success"
        : "empty";

  const riskPercent = totalInQueue
    ? Math.min(
        100,
        Math.round((((stats?.failed_registry ?? 0) + (stats?.dead ?? 0)) / totalInQueue) * 100)
      )
    : 0;

  const healthTag =
    riskPercent > 35 ? (
      <Tag color="error" icon={<WarningOutlined />}>
        高风险
      </Tag>
    ) : riskPercent > 15 ? (
      <Tag color="warning" icon={<AlertOutlined />}>
        中风险
      </Tag>
    ) : (
      <Tag color="success" icon={<SafetyCertificateOutlined />}>
        低风险
      </Tag>
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
        <Card className="hero-card">
          <div className="hero-layout">
            <div>
              <div className="hero-kicker">管理端 / 队列与任务健康</div>
              <Typography.Title level={4} className="hero-title">
                队列监控中心
              </Typography.Title>
              <Typography.Text className="hero-desc">
                实时追踪入库任务压力、失败堆积和死信风险，帮助管理端快速判断是否需要人工干预。
              </Typography.Text>
              <div className="hero-note" style={{ marginTop: 14 }}>
                <span className="hero-note__item">默认每 10 秒自动刷新</span>
                <span className="hero-note__item">风险占比越高，越需要优先处理失败任务</span>
                <span className="hero-note__item">死信迁移前需要二次确认</span>
              </div>
            </div>
            <div className="summary-grid">
              <div className="summary-item">
                <div className="summary-item-label">队列总量</div>
                <div className="summary-item-value">{totalInQueue}</div>
              </div>
              <div className="summary-item">
                <div className="summary-item-label">死信数</div>
                <div className="summary-item-value">{stats?.dead ?? 0}</div>
              </div>
              <div className="summary-item">
                <div className="summary-item-label">失败注册</div>
                <div className="summary-item-value">{stats?.failed_registry ?? 0}</div>
              </div>
              <div className="summary-item">
                <div className="summary-item-label">风险占比</div>
                <div className="summary-item-value">{riskPercent}%</div>
              </div>
            </div>
          </div>
        </Card>

        <Card
          title={
            <Space size={8}>
              <DashboardOutlined />
              <span>队列监控</span>
            </Space>
          }
          className="card-soft"
          extra={
            <Space>
              <Tag bordered={false} color="blue">
                自动刷新 10s
              </Tag>
              <Button
                icon={<ReloadOutlined />}
                onClick={() => void statsQuery.refetch()}
                loading={statsQuery.isFetching}
              >
                刷新
              </Button>
              <ConfirmAction
                title="确认转移失败任务到死信队列？"
                description="该操作会批量迁移失败任务，建议先确认告警与任务状态。"
                okText="确认转移"
                cancelText="取消"
                onConfirm={() => {
                  moveMutation.mutate();
                }}
                buttonText="转移失败任务到死信"
                danger
                icon={<WarningOutlined />}
                loading={moveMutation.isPending}
              />
            </Space>
          }
        >
          <Space direction="vertical" size={18} style={{ width: "100%" }}>
            <div className="monitor-health-row">
              <Space size={10} wrap>
                <Typography.Text type="secondary">当前健康度</Typography.Text>
                {healthTag}
              </Space>
              <Typography.Text type="secondary">
                {lastMoveRequestId ? "最近一次死信迁移已完成" : "暂无死信迁移操作"}
              </Typography.Text>
            </div>
            <Progress
              percent={riskPercent}
              strokeColor={
                riskPercent > 35 ? "#cf3f3f" : riskPercent > 15 ? "#e5a100" : "#0ea5a0"
              }
              format={(percent) => `风险任务 ${percent}%`}
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
          {statsQuery.data?.alerts.length ? (
            <div className="monitor-alert-list">
              {statsQuery.data.alerts.map((item) => (
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
