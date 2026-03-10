import {
  ArrowLeftOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  PlusOutlined,
  TagsOutlined
} from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import { Button, Card, Form, Input, InputNumber, Space, Tooltip, Typography, message } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { createEvalSet } from "../../shared/api/modules/eval";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";
import {
  EvalSetFormValues,
  parseTags,
  pushRecentEvalSet,
  readRecentEvalRuns,
  readRecentEvalSets
} from "./evalShared";

export function EvalCreatePage() {
  const navigate = useNavigate();
  const [form] = Form.useForm<EvalSetFormValues>();
  const [recentSetCount] = useState(() => readRecentEvalSets().length);
  const [recentRunCount] = useState(() => readRecentEvalRuns().length);

  const createSetMutation = useMutation({
    mutationFn: async (values: EvalSetFormValues) =>
      createEvalSet({
        name: values.name.trim(),
        description: values.description?.trim() || undefined,
        items: values.items.map((item) => ({
          question: item.question.trim(),
          gold_page_start: item.gold_page_start,
          gold_page_end: item.gold_page_end,
          tags: parseTags(item.tags_text)
        }))
      }),
    onSuccess: (data) => {
      message.success("评测集创建成功");
      pushRecentEvalSet({
        eval_set_id: data.eval_set_id,
        name: data.name,
        created_at: data.created_at
      });
      form.resetFields();
      navigate(`/admin/eval?evalSetId=${encodeURIComponent(data.eval_set_id)}`);
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const watchedName = Form.useWatch("name", form) ?? "";
  const watchedDescription = Form.useWatch("description", form) ?? "";
  const watchedItems = Form.useWatch("items", form) ?? [{ question: "", tags_text: "" }];

  const sampleCount = watchedItems.length;
  const completedQuestionCount = watchedItems.filter((item) => item?.question?.trim()).length;

  return (
    <div className="page-stack">
      {createSetMutation.isError ? (
        <RequestErrorAlert error={normalizeApiError(createSetMutation.error)} />
      ) : null}

      <Card className="card-soft split-overview-card">
        <div className="split-overview">
          <div className="split-overview__copy">
            <div className="split-overview__label-row">
              <span className="hero-kicker">评测集设计</span>
              <Typography.Text className="split-overview__eyebrow">
                把样本录入和运行结果拆开，评测创建页就可以更专注于题集本身。
              </Typography.Text>
            </div>
            <Typography.Title level={3} className="hero-title">
              新建评测集
            </Typography.Title>
            <Typography.Paragraph className="split-overview__desc">
              左侧录入样本，右侧实时汇总当前进度和录入建议，让长表单不再散，也不会显得空。
            </Typography.Paragraph>
            <div className="split-overview__notes">
              <span className="split-overview__note">先建样本，再运行评测</span>
              <span className="split-overview__note">最近记录会在页面间承接</span>
            </div>
          </div>
          <div className="split-overview__stats">
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">最近评测集</span>
              <span className="split-overview-stat__value">{recentSetCount}</span>
            </div>
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">最近运行</span>
              <span className="split-overview-stat__value">{recentRunCount}</span>
            </div>
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">样本入口</span>
              <span className="split-overview-stat__value">单列</span>
            </div>
            <div className="split-overview-stat">
              <span className="split-overview-stat__label">创建后</span>
              <span className="split-overview-stat__value">回评测页</span>
            </div>
          </div>
        </div>
      </Card>

      <Card
        className="card-soft split-action-card"
        title={
          <Space size={8}>
            <DatabaseOutlined />
            <span>录入评测样本</span>
          </Space>
        }
        extra={
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => {
              navigate("/admin/eval");
            }}
          >
            返回评测中心
          </Button>
        }
      >
        <div className="split-action-card__body split-action-card__body--full">
          <div className="split-create-layout split-create-layout--wide">
            <div className="split-create-main">
              <div className="split-pane-copy">
                <Typography.Text className="split-pane-copy__title">每条样本至少填写问题</Typography.Text>
                <Typography.Text className="split-pane-copy__desc">
                  页码和标签作为辅助信息按需补充，创建完成后再回到评测中心选择知识库和运行参数。
                </Typography.Text>
              </div>

              <Form<EvalSetFormValues>
                form={form}
                layout="vertical"
                initialValues={{
                  items: [{ question: "", tags_text: "" }]
                }}
                onFinish={(values) => {
                  createSetMutation.mutate(values);
                }}
              >
                <Form.Item
                  name="name"
                  label="评测集名称"
                  rules={[{ required: true, message: "请输入名称" }]}
                >
                  <Input placeholder="例如：教务问答评测集_v2" />
                </Form.Item>
                <Form.Item name="description" label="描述（可选）">
                  <Input.TextArea rows={3} placeholder="说明样本范围、目标场景或评测目的" />
                </Form.Item>

                <Form.List name="items">
                  {(fields, { add, remove }) => (
                    <Space direction="vertical" style={{ width: "100%" }} size={12}>
                      {fields.map((field, index) => (
                        <Card
                          key={field.key}
                          size="small"
                          className="card-inset"
                          title={`样本 ${index + 1}`}
                          extra={
                            <Tooltip title="删除样本">
                              <Button
                                danger
                                size="small"
                                shape="circle"
                                icon={<DeleteOutlined />}
                                onClick={() => {
                                  remove(field.name);
                                }}
                                disabled={fields.length <= 1}
                                aria-label="删除样本"
                              />
                            </Tooltip>
                          }
                        >
                          <Form.Item
                            name={[field.name, "question"]}
                            label="问题"
                            rules={[{ required: true, message: "请输入问题" }]}
                          >
                            <Input.TextArea rows={3} placeholder="输入用于评测的问题" />
                          </Form.Item>
                          <div className="ops-kpi-grid">
                            <Form.Item name={[field.name, "gold_page_start"]} label="起始页">
                              <InputNumber min={1} style={{ width: "100%" }} />
                            </Form.Item>
                            <Form.Item name={[field.name, "gold_page_end"]} label="结束页">
                              <InputNumber min={1} style={{ width: "100%" }} />
                            </Form.Item>
                            <Form.Item name={[field.name, "tags_text"]} label="标签（逗号分隔）">
                              <Input placeholder="policy, exam" prefix={<TagsOutlined />} />
                            </Form.Item>
                          </div>
                        </Card>
                      ))}

                      <div className="split-actions split-actions--between">
                        <Button
                          icon={<PlusOutlined />}
                          onClick={() => {
                            add({ question: "", tags_text: "" });
                          }}
                        >
                          新增样本
                        </Button>
                        <div className="split-actions__main">
                          <Button
                            onClick={() => {
                              navigate("/admin/eval");
                            }}
                          >
                            取消
                          </Button>
                          <Button
                            type="primary"
                            htmlType="submit"
                            icon={<DatabaseOutlined />}
                            loading={createSetMutation.isPending}
                          >
                            创建评测集
                          </Button>
                        </div>
                      </div>
                    </Space>
                  )}
                </Form.List>
              </Form>
            </div>

            <aside className="split-create-aside split-create-aside--sticky">
              <section className="split-side-card">
                <Typography.Text className="split-side-card__title">评测集摘要</Typography.Text>
                <div className="split-side-metrics">
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">名称</span>
                    <span className="split-side-metric__value">
                      {watchedName.trim() || "未填写"}
                    </span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">样本数</span>
                    <span className="split-side-metric__value">{sampleCount}</span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">已填问题</span>
                    <span className="split-side-metric__value">{completedQuestionCount}</span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">描述状态</span>
                    <span className="split-side-metric__value">
                      {watchedDescription.trim() ? "已补充" : "未填写"}
                    </span>
                  </div>
                </div>
              </section>

              <section className="split-side-card">
                <Typography.Text className="split-side-card__title">录入建议</Typography.Text>
                <div className="split-side-list">
                  <div className="split-side-list__item">优先覆盖高频问题、拒答场景和容易混淆的问题。</div>
                  <div className="split-side-list__item">如果已知证据页码，尽量补充起止页，方便后续核验。</div>
                  <div className="split-side-list__item">创建后直接回到评测中心运行，验证不同知识库和阈值策略。</div>
                </div>
              </section>
            </aside>
          </div>
        </div>
      </Card>
    </div>
  );
}
