import { BulbOutlined, EditOutlined, SearchOutlined } from "@ant-design/icons";
import { Button, Card, Space, Tag, Typography } from "antd";
import { NextStepAction, NextStepItem } from "../api/modules/ask";

function resolveStepIcon(action: NextStepAction) {
  if (action === "rewrite_question") {
    return <EditOutlined />;
  }
  if (action === "search_keyword") {
    return <SearchOutlined />;
  }
  return <BulbOutlined />;
}

function resolveActionLabel(step: NextStepItem) {
  if (step.action === "check_official_source") {
    return "查看官方来源";
  }
  if (step.action === "verify_kb_scope") {
    return "查看知识库范围";
  }
  if (step.action === "rewrite_question") {
    return "填入改写建议";
  }
  if (step.action === "search_keyword") {
    return "填入关键词";
  }
  if (step.action === "add_context") {
    return "填入补充条件";
  }
  if (!step.value) {
    return "查看建议";
  }
  return "用于追问";
}

interface RefusalNextStepsCardProps {
  nextSteps: NextStepItem[];
  suggestions?: string[];
  onApplyStep?: (step: NextStepItem) => void;
}

export function RefusalNextStepsCard(props: RefusalNextStepsCardProps) {
  const { nextSteps, suggestions = [], onApplyStep } = props;
  const showFallbackSuggestions = suggestions.length > 0;

  if (!nextSteps.length && !showFallbackSuggestions) {
    return null;
  }

  return (
    <Card size="small" title="下一步建议" className="chat-refusal-card">
      <Space direction="vertical" size={10} style={{ width: "100%" }}>
        {nextSteps.length ? (
          <div className="refusal-next-steps">
            {nextSteps.map((step) => (
              <div key={`${step.action}_${step.label}_${step.value ?? ""}`} className="refusal-next-step">
                <div className="refusal-next-step__head">
                  <Space size={8}>
                    <span className="refusal-next-step__icon">{resolveStepIcon(step.action)}</span>
                    <Typography.Text strong>{step.label}</Typography.Text>
                  </Space>
                  <Tag>{step.action}</Tag>
                </div>
                <Typography.Paragraph className="refusal-next-step__detail">
                  {step.detail}
                </Typography.Paragraph>
                {step.value ? (
                  <Typography.Paragraph className="refusal-next-step__value">
                    推荐内容：{step.value}
                  </Typography.Paragraph>
                ) : null}
                {onApplyStep ? (
                  <Button
                    size="small"
                    type="default"
                    onClick={(event) => {
                      event.stopPropagation();
                      onApplyStep(step);
                    }}
                  >
                    {resolveActionLabel(step)}
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
        {showFallbackSuggestions ? (
          <div className="refusal-next-steps__fallback">
            <Typography.Text type="secondary">补充说明</Typography.Text>
            <ul className="muted-list">
              {suggestions.map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </Space>
    </Card>
  );
}
