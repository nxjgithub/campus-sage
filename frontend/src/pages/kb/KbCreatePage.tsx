import { ArrowLeftOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Collapse,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Tooltip,
  Typography,
  message
} from "antd";
import { useNavigate } from "react-router-dom";
import { createKb, fetchKbList } from "../../shared/api/modules/kb";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { RequestErrorAlert } from "../../shared/components/RequestErrorAlert";
import { buildKbConfig, DEFAULT_KB_FORM_VALUES, KbFormValues } from "./kbShared";

const VISIBILITY_LABEL: Record<KbFormValues["visibility"], string> = {
  public: "公开",
  internal: "内部",
  admin: "管理员"
};

export function KbCreatePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<KbFormValues>();

  const kbQuery = useQuery({
    queryKey: ["kb", "list"],
    queryFn: fetchKbList
  });

  const createMutation = useMutation({
    mutationFn: async (values: KbFormValues) =>
      createKb({
        name: values.name.trim(),
        description: values.description?.trim() || null,
        visibility: values.visibility,
        config: buildKbConfig({
          ...DEFAULT_KB_FORM_VALUES,
          ...values
        })
      }),
    onSuccess: async () => {
      message.success("知识库创建成功");
      form.resetFields();
      await queryClient.invalidateQueries({ queryKey: ["kb", "list"] });
      navigate("/admin/kb");
    },
    onError: (error) => {
      const normalized = normalizeApiError(error);
      message.error(formatApiErrorMessage(normalized));
    }
  });

  const watchedName = Form.useWatch("name", form) ?? DEFAULT_KB_FORM_VALUES.name;
  const watchedDescription =
    Form.useWatch("description", form) ?? DEFAULT_KB_FORM_VALUES.description ?? "";
  const watchedVisibility =
    Form.useWatch("visibility", form) ?? DEFAULT_KB_FORM_VALUES.visibility;
  const watchedTopk = Form.useWatch("topk", form) ?? DEFAULT_KB_FORM_VALUES.topk;
  const watchedThreshold =
    Form.useWatch("threshold", form) ?? DEFAULT_KB_FORM_VALUES.threshold;
  const watchedRerank =
    Form.useWatch("rerank_enabled", form) ?? DEFAULT_KB_FORM_VALUES.rerank_enabled;

  const publicCount = kbQuery.data?.items.filter((item) => item.visibility === "public").length ?? 0;
  const internalCount =
    kbQuery.data?.items.filter((item) => item.visibility === "internal").length ?? 0;
  const adminCount = kbQuery.data?.items.filter((item) => item.visibility === "admin").length ?? 0;

  return (
    <div className="page-stack">
      {createMutation.isError ? (
        <RequestErrorAlert error={normalizeApiError(createMutation.error)} />
      ) : null}

      <Card className="card-soft kb-overview-card">
        <div className="kb-overview">
          <div className="kb-overview__copy">
            <div className="kb-overview__label-row">
              <span className="hero-kicker">知识库创建</span>
              <Typography.Text className="kb-overview__eyebrow">
                把创建动作从治理列表中拆出，首屏只保留最关键的录入路径。
              </Typography.Text>
            </div>
            <Typography.Title level={3} className="hero-title">
              新建知识库
            </Typography.Title>
            <Typography.Paragraph className="kb-overview__desc">
              左侧完成基础信息与检索策略，右侧实时汇总当前配置和后续动作，让空白变成更有秩序的留白。
            </Typography.Paragraph>
            <div className="kb-overview__notes">
              <span className="kb-overview__note">高频字段直接录入</span>
              <span className="kb-overview__note">低频参数折叠进高级设置</span>
            </div>
          </div>
          <div className="kb-overview__stats">
            <div className="kb-overview-stat">
              <span className="kb-overview-stat__label">现有知识库</span>
              <span className="kb-overview-stat__value">{kbQuery.data?.items.length ?? 0}</span>
            </div>
            <div className="kb-overview-stat">
              <span className="kb-overview-stat__label">公开库</span>
              <span className="kb-overview-stat__value">{publicCount}</span>
            </div>
            <div className="kb-overview-stat">
              <span className="kb-overview-stat__label">内部库</span>
              <span className="kb-overview-stat__value">{internalCount}</span>
            </div>
            <div className="kb-overview-stat">
              <span className="kb-overview-stat__label">管理员库</span>
              <span className="kb-overview-stat__value">{adminCount}</span>
            </div>
          </div>
        </div>
      </Card>

      <Card
        className="card-soft kb-create-card"
        title={
          <Space size={8}>
            <PlusOutlined />
            <span>填写创建信息</span>
          </Space>
        }
        extra={
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => {
              navigate("/admin/kb");
            }}
          >
            返回列表
          </Button>
        }
      >
        <div className="split-action-card__body split-action-card__body--full">
          <div className="split-create-layout">
            <div className="split-create-main">
              <div className="split-pane-copy">
                <Typography.Text className="split-pane-copy__title">先录入常用字段</Typography.Text>
                <Typography.Text className="split-pane-copy__desc">
                  首屏只保留创建所需的关键项，其余检索参数收进高级设置，减少大面积空白中的信息漂浮感。
                </Typography.Text>
              </div>

              <Form<KbFormValues>
                form={form}
                layout="vertical"
                initialValues={DEFAULT_KB_FORM_VALUES}
                onFinish={(values) => createMutation.mutate(values)}
              >
                <Form.Item
                  name="name"
                  label="知识库名称"
                  rules={[{ required: true, message: "请输入名称" }]}
                >
                  <Input placeholder="例如：教务知识库" />
                </Form.Item>
                <Form.Item name="description" label="知识库说明">
                  <Input.TextArea rows={4} placeholder="可选，用于说明适用范围、来源或维护方式" />
                </Form.Item>

                <div className="kb-form-section">
                  <div className="kb-form-section__head">
                    <Typography.Text className="kb-form-section__title">常用设置</Typography.Text>
                    <Typography.Text className="kb-form-section__hint">
                      这些字段决定知识库的默认检索体验。
                    </Typography.Text>
                  </div>
                  <div className="kb-config-grid">
                    <Form.Item name="visibility" label="可见性" rules={[{ required: true }]}>
                      <Select
                        options={[
                          { value: "public", label: "公开" },
                          { value: "internal", label: "内部" },
                          { value: "admin", label: "管理员" }
                        ]}
                      />
                    </Form.Item>
                    <Form.Item name="topk" label="TopK">
                      <InputNumber min={1} style={{ width: "100%" }} />
                    </Form.Item>
                    <Form.Item name="threshold" label="阈值">
                      <InputNumber min={0} max={1} step={0.01} style={{ width: "100%" }} />
                    </Form.Item>
                  </div>
                </div>

                <Collapse
                  ghost
                  className="kb-advanced-collapse"
                  items={[
                    {
                      key: "advanced",
                      label: (
                        <div className="kb-advanced-collapse__label">
                          <Typography.Text className="kb-advanced-collapse__title">
                            高级设置
                          </Typography.Text>
                          <Typography.Text className="kb-advanced-collapse__hint">
                            低频参数，按需展开
                          </Typography.Text>
                        </div>
                      ),
                      children: (
                        <div className="kb-advanced-grid">
                          <Form.Item name="rerank_enabled" label="启用重排">
                            <Select
                              options={[
                                { value: true, label: "启用" },
                                { value: false, label: "关闭" }
                              ]}
                            />
                          </Form.Item>
                          <Form.Item name="max_context_tokens" label="最大上下文">
                            <InputNumber min={100} style={{ width: "100%" }} />
                          </Form.Item>
                          <Form.Item name="min_context_chars" label="最小上下文长度">
                            <InputNumber min={1} style={{ width: "100%" }} />
                          </Form.Item>
                          <Form.Item name="min_keyword_coverage" label="最小关键词覆盖率">
                            <InputNumber min={0} max={1} step={0.05} style={{ width: "100%" }} />
                          </Form.Item>
                        </div>
                      )
                    }
                  ]}
                />

                <Form.Item style={{ marginTop: 16, marginBottom: 0 }}>
                  <div className="kb-create-actions">
                    <Button
                      onClick={() => {
                        navigate("/admin/kb");
                      }}
                    >
                      取消
                    </Button>
                    <Tooltip title="创建知识库">
                      <Button
                        aria-label="创建知识库"
                        type="primary"
                        htmlType="submit"
                        loading={createMutation.isPending}
                        icon={<PlusOutlined />}
                      >
                        创建知识库
                      </Button>
                    </Tooltip>
                  </div>
                </Form.Item>
              </Form>
            </div>

            <aside className="split-create-aside">
              <section className="split-side-card">
                <Typography.Text className="split-side-card__title">当前配置</Typography.Text>
                <div className="split-side-metrics">
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">名称</span>
                    <span className="split-side-metric__value">
                      {watchedName.trim() || "未填写"}
                    </span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">可见性</span>
                    <span className="split-side-metric__value">
                      {VISIBILITY_LABEL[watchedVisibility]}
                    </span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">检索策略</span>
                    <span className="split-side-metric__value">
                      TopK {watchedTopk} / 阈值 {watchedThreshold}
                    </span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">重排</span>
                    <span className="split-side-metric__value">
                      {watchedRerank ? "已启用" : "未启用"}
                    </span>
                  </div>
                  <div className="split-side-metric">
                    <span className="split-side-metric__label">说明状态</span>
                    <span className="split-side-metric__value">
                      {watchedDescription.trim() ? "已补充" : "未填写"}
                    </span>
                  </div>
                </div>
              </section>

              <section className="split-side-card">
                <Typography.Text className="split-side-card__title">创建后</Typography.Text>
                <div className="split-side-list">
                  <div className="split-side-list__item">返回列表查看新知识库并继续维护说明。</div>
                  <div className="split-side-list__item">前往文档上传页为该知识库投递资料。</div>
                  <div className="split-side-list__item">在问答端验证检索阈值和重排策略是否合适。</div>
                </div>
              </section>
            </aside>
          </div>
        </div>
      </Card>
    </div>
  );
}
