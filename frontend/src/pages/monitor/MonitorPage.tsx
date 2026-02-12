import { useState } from "react";
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
  Typography,
  message
} from "antd";
import { fetchQueueStats, moveDeadJobs } from "../../shared/api/modules/monitor";
import { normalizeApiError } from "../../shared/api/errors";
import { ConfirmAction } from "../../shared/components/ConfirmAction";
import { CopyableField } from "../../shared/components/CopyableField";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";

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
      message.error(`${normalized.message}（${normalized.code}）`);
    }
  });

  if (statsQuery.isError) {
    return <RequestErrorAlert error={normalizeApiError(statsQuery.error)} />;
  }

  const stats = statsQuery.data?.stats;
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
    ? Math.min(100, Math.round((((stats?.failed_registry ?? 0) + (stats?.dead ?? 0)) / totalInQueue) * 100))
    : 0;

  const healthTag =
    riskPercent > 35 ? (
      <Tag color="error">高风险</Tag>
    ) : riskPercent > 15 ? (
      <Tag color="warning">中风险</Tag>
    ) : (
      <Tag color="success">低风险</Tag>
    );

  return (
    <div className="page-stack">
      <Card className="hero-card">
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          <Typography.Title level={4} className="hero-title">
            队列监控中心
          </Typography.Title>
          <Typography.Text className="hero-desc">
            实时追踪入库任务压力、失败堆积和死信风险，支撑运维处置。
          </Typography.Text>
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
              <div className="summary-item-label">失败注册数</div>
              <div className="summary-item-value">{stats?.failed_registry ?? 0}</div>
            </div>
            <div className="summary-item">
              <div className="summary-item-label">风险占比</div>
              <div className="summary-item-value">{riskPercent}%</div>
            </div>
          </div>
          <Space>
            <Typography.Text type="secondary">当前健康度：</Typography.Text>
            {healthTag}
          </Space>
          <Progress
            percent={riskPercent}
            strokeColor={riskPercent > 35 ? "#cf3f3f" : riskPercent > 15 ? "#e5a100" : "#0ea5a0"}
            format={(percent) => `风险任务占比 ${percent}%`}
          />
        </Space>
      </Card>

      <Card
        title="队列监控"
        className="card-soft"
        extra={
          <Space>
            <Button onClick={() => void statsQuery.refetch()} loading={statsQuery.isFetching}>
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
              loading={moveMutation.isPending}
            />
          </Space>
        }
      >
        <Row gutter={[16, 16]}>
          <Col xs={12} md={8} lg={6}>
            <Statistic title="queued" value={stats?.queued ?? 0} />
          </Col>
          <Col xs={12} md={8} lg={6}>
            <Statistic title="started" value={stats?.started ?? 0} />
          </Col>
          <Col xs={12} md={8} lg={6}>
            <Statistic title="deferred" value={stats?.deferred ?? 0} />
          </Col>
          <Col xs={12} md={8} lg={6}>
            <Statistic title="finished" value={stats?.finished ?? 0} />
          </Col>
          <Col xs={12} md={8} lg={6}>
            <Statistic title="failed_registry" value={stats?.failed_registry ?? 0} />
          </Col>
          <Col xs={12} md={8} lg={6}>
            <Statistic title="dead" value={stats?.dead ?? 0} />
          </Col>
          <Col xs={12} md={8} lg={6}>
            <Statistic title="scheduled" value={stats?.scheduled ?? 0} />
          </Col>
        </Row>
        <Space direction="vertical" size={4} style={{ marginTop: 12 }}>
          <CopyableField label="stats_request_id" value={statsQuery.data?.request_id} />
          <CopyableField label="last_move_request_id" value={lastMoveRequestId} />
        </Space>
      </Card>

      <Card title="告警" className="card-soft">
        {statsQuery.data?.alerts.length ? (
          <ul className="muted-list">
            {statsQuery.data.alerts.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <Alert type="success" showIcon message="暂无告警" />
        )}
      </Card>
    </div>
  );
}
