import { ReactNode } from "react";
import { Typography } from "antd";

export interface ChartDatum {
  key: string;
  label: string;
  value: number;
  color: string;
}

export interface TrendDatum {
  key: string;
  label: string;
  value: number;
}

interface MetricBarChartProps {
  items: ChartDatum[];
  emptyText?: string;
  valueFormatter?: (value: number) => ReactNode;
}

interface DonutMetricChartProps {
  items: ChartDatum[];
  centerLabel: string;
  centerValue: ReactNode;
  emptyText?: string;
}

interface MiniTrendChartProps {
  items: TrendDatum[];
  stroke: string;
  emptyText?: string;
  valueFormatter?: (value: number) => ReactNode;
}

function resolveTotal(items: ChartDatum[]) {
  return items.reduce((sum, item) => sum + Math.max(0, item.value), 0);
}

function resolveGradient(items: ChartDatum[]) {
  const total = resolveTotal(items);
  if (!total) {
    return "conic-gradient(#e5e7eb 0deg 360deg)";
  }

  let current = 0;
  const segments = items.map((item) => {
    const start = current;
    const angle = (Math.max(0, item.value) / total) * 360;
    current += angle;
    return `${item.color} ${start}deg ${current}deg`;
  });
  return `conic-gradient(${segments.join(", ")})`;
}

function resolveTrendPath(items: TrendDatum[]) {
  if (items.length < 2) {
    return "";
  }

  const width = 100;
  const height = 40;
  const maxValue = Math.max(...items.map((item) => item.value), 0);
  const minValue = Math.min(...items.map((item) => item.value), 0);
  const range = Math.max(maxValue - minValue, 1);

  return items
    .map((item, index) => {
      const x = (index / (items.length - 1)) * width;
      const y = height - ((item.value - minValue) / range) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export function MetricBarChart({
  items,
  emptyText = "暂无数据",
  valueFormatter
}: MetricBarChartProps) {
  const maxValue = Math.max(...items.map((item) => item.value), 0);

  if (!items.length || maxValue <= 0) {
    return <Typography.Text type="secondary">{emptyText}</Typography.Text>;
  }

  return (
    <div className="metric-bars">
      {items.map((item) => {
        const width = `${(item.value / maxValue) * 100}%`;
        return (
          <div key={item.key} className="metric-bars__row">
            <div className="metric-bars__meta">
              <span className="metric-bars__label">{item.label}</span>
              <span className="metric-bars__value">
                {valueFormatter ? valueFormatter(item.value) : item.value}
              </span>
            </div>
            <div className="metric-bars__track">
              <div
                className="metric-bars__fill"
                style={{ width, background: item.color }}
                aria-hidden="true"
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function DonutMetricChart({
  items,
  centerLabel,
  centerValue,
  emptyText = "暂无数据"
}: DonutMetricChartProps) {
  const total = resolveTotal(items);

  if (!items.length || total <= 0) {
    return <Typography.Text type="secondary">{emptyText}</Typography.Text>;
  }

  return (
    <div className="metric-donut">
      <div
        className="metric-donut__chart"
        style={{ backgroundImage: resolveGradient(items) }}
        aria-hidden="true"
      >
        <div className="metric-donut__center">
          <span className="metric-donut__center-label">{centerLabel}</span>
          <span className="metric-donut__center-value">{centerValue}</span>
        </div>
      </div>
      <div className="metric-donut__legend">
        {items.map((item) => (
          <div key={item.key} className="metric-donut__legend-item">
            <span
              className="metric-donut__legend-dot"
              style={{ background: item.color }}
              aria-hidden="true"
            />
            <span className="metric-donut__legend-label">{item.label}</span>
            <span className="metric-donut__legend-value">{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MiniTrendChart({
  items,
  stroke,
  emptyText = "等待趋势数据",
  valueFormatter
}: MiniTrendChartProps) {
  if (!items.length) {
    return <Typography.Text type="secondary">{emptyText}</Typography.Text>;
  }

  const latest = items[items.length - 1];
  const previous = items.length > 1 ? items[items.length - 2] : null;
  const delta = previous ? latest.value - previous.value : 0;
  const trendPath = resolveTrendPath(items);

  return (
    <div className="metric-trend">
      <div className="metric-trend__summary">
        <span className="metric-trend__label">{latest.label}</span>
        <span className="metric-trend__value">
          {valueFormatter ? valueFormatter(latest.value) : latest.value}
        </span>
      </div>
      <div className="metric-trend__delta" data-tone={delta > 0 ? "up" : delta < 0 ? "down" : "flat"}>
        {delta > 0 ? `+${delta}` : delta}
      </div>
      <svg
        className="metric-trend__chart"
        viewBox="0 0 100 40"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path
          d={trendPath}
          fill="none"
          stroke={stroke}
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <div className="metric-trend__labels">
        <span>{items[0]?.label ?? "-"}</span>
        <span>{latest.label}</span>
      </div>
    </div>
  );
}
