import { useMemo, useState } from "react";
import { Button, Form, Input, Modal, Select, Space, Tag, Typography } from "antd";
import { FeedbackPayload } from "../api/modules/conversations";

type FeedbackRating = FeedbackPayload["rating"];

interface FeedbackActionProps {
  messageId: string;
  submitting: boolean;
  submitted: boolean;
  onSubmit: (messageId: string, payload: FeedbackPayload) => Promise<void>;
}

interface FeedbackFormValues {
  reasons?: string[];
  comment?: string;
  expected_hint?: string;
}

const FEEDBACK_REASON_OPTIONS: Record<FeedbackRating, string[]> = {
  up: ["证据充分", "回答清晰", "覆盖问题", "可执行性强"],
  down: ["证据不足", "与问题无关", "信息不完整", "存在事实偏差"]
};

function trimOrUndefined(value?: string) {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

export function FeedbackAction({
  messageId,
  submitting,
  submitted,
  onSubmit
}: FeedbackActionProps) {
  const [open, setOpen] = useState(false);
  const [rating, setRating] = useState<FeedbackRating>("up");
  const [form] = Form.useForm<FeedbackFormValues>();

  const reasonOptions = useMemo(() => {
    return FEEDBACK_REASON_OPTIONS[rating].map((item) => ({
      label: item,
      value: item
    }));
  }, [rating]);

  const openModal = (nextRating: FeedbackRating) => {
    setRating(nextRating);
    setOpen(true);
  };

  const handleClose = () => {
    if (submitting) {
      return;
    }
    setOpen(false);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      await onSubmit(messageId, {
        rating,
        reasons: values.reasons ?? [],
        comment: trimOrUndefined(values.comment),
        expected_hint: rating === "down" ? trimOrUndefined(values.expected_hint) : undefined
      });
      form.resetFields();
      setOpen(false);
    } catch {
      // 失败时保留已填写内容，便于用户修改后重试
    }
  };

  if (submitted) {
    return (
      <Button size="small" disabled>
        已提交
      </Button>
    );
  }

  return (
    <>
      <Space>
        <Button
          size="small"
          onClick={() => {
            openModal("up");
          }}
          loading={submitting && rating === "up"}
        >
          赞同
        </Button>
        <Button
          size="small"
          onClick={() => {
            openModal("down");
          }}
          loading={submitting && rating === "down"}
        >
          反对
        </Button>
      </Space>
      <Modal
        title="提交反馈"
        open={open}
        onCancel={handleClose}
        onOk={() => {
          void handleSubmit();
        }}
        okText="提交反馈"
        cancelText="取消"
        confirmLoading={submitting}
        destroyOnHidden={false}
      >
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          <Typography.Text type="secondary">
            消息 ID：<Typography.Text copyable={{ text: messageId }}>{messageId}</Typography.Text>
          </Typography.Text>
          <Tag color={rating === "up" ? "success" : "warning"}>
            {rating === "up" ? "赞同反馈" : "反对反馈"}
          </Tag>
        </Space>
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="reasons" label="反馈原因（可选）">
            <Select
              mode="multiple"
              allowClear
              placeholder="请选择反馈原因"
              options={reasonOptions}
            />
          </Form.Item>
          <Form.Item name="comment" label="补充说明（可选）">
            <Input.TextArea
              rows={3}
              maxLength={400}
              showCount
              placeholder="可填写对答案质量的说明"
            />
          </Form.Item>
          {rating === "down" ? (
            <Form.Item name="expected_hint" label="期望回答方向（可选）">
              <Input.TextArea
                rows={3}
                maxLength={400}
                showCount
                placeholder="例如：请给出具体政策条款或办理步骤"
              />
            </Form.Item>
          ) : null}
        </Form>
      </Modal>
    </>
  );
}
