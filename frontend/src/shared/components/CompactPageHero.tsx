import { InfoCircleOutlined } from "@ant-design/icons";
import { Button, Card, Tooltip, Typography } from "antd";
import { ReactNode } from "react";

interface CompactPageHeroStat {
  label: string;
  value: ReactNode;
}

interface CompactPageHeroProps {
  kicker: string;
  title: string;
  description: string;
  stats: CompactPageHeroStat[];
}

export function CompactPageHero({
  kicker,
  title,
  description,
  stats
}: CompactPageHeroProps) {
  return (
    <Card className="hero-card compact-page-hero">
      <div className="compact-page-hero__main">
        <div className="compact-page-hero__copy">
          <div className="compact-page-hero__label-row">
            <span className="hero-kicker">{kicker}</span>
            <Tooltip title={description}>
              <Button
                type="text"
                size="small"
                className="compact-page-hero__info"
                icon={<InfoCircleOutlined />}
                aria-label="查看页面说明"
              />
            </Tooltip>
          </div>
          <Typography.Title level={3} className="hero-title">
            {title}
          </Typography.Title>
        </div>
        <div className="summary-grid compact-page-hero__stats">
          {stats.map((item) => (
            <div key={item.label} className="summary-item">
              <div className="summary-item-label">{item.label}</div>
              <div className="summary-item-value">{item.value}</div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
