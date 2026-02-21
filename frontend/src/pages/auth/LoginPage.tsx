import { useEffect, useState } from "react";
import { Button, Card, Col, Form, Input, Row, Space, Typography, message } from "antd";
import { useNavigate, useSearchParams } from "react-router-dom";
import { formatApiErrorMessage, normalizeApiError } from "../../shared/api/errors";
import { useAuth } from "../../shared/auth/auth";
import { getRoleHomePath } from "../../shared/auth/role";

interface LoginFormValues {
  email: string;
  password: string;
}

function resolveNextPath(rawNext: string | null, fallback: string) {
  if (!rawNext) {
    return fallback;
  }
  if (!rawNext.startsWith("/")) {
    return fallback;
  }
  return rawNext;
}

export function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { signIn, role, isAuthenticated, status } = useAuth();
  const [form] = Form.useForm<LoginFormValues>();
  const [submitting, setSubmitting] = useState(false);

  const fallbackPath = getRoleHomePath(role);
  const nextPath = resolveNextPath(searchParams.get("next"), fallbackPath);
  const isDev = import.meta.env.DEV;

  useEffect(() => {
    if (status !== "loading" && isAuthenticated) {
      navigate(nextPath, { replace: true });
    }
  }, [isAuthenticated, navigate, nextPath, status]);

  return (
    <div className="login-shell">
      <div className="login-blob login-blob--one" />
      <div className="login-blob login-blob--two" />
      <Row gutter={[20, 20]} className="login-layout">
        <Col xs={24} lg={12}>
          <Card className="hero-card login-brand-card">
            <Space direction="vertical" size={16} style={{ width: "100%" }}>
              <Space align="center" size={12}>
                <span className="login-brand-mark">CS</span>
                <div>
                  <Typography.Title level={3} style={{ margin: 0 }}>
                    CampusSage
                  </Typography.Title>
                  <Typography.Text className="login-tagline">让校园问答有据可查</Typography.Text>
                </div>
              </Space>
              <Typography.Paragraph className="hero-desc" style={{ marginBottom: 0 }}>
                连接检索、引用与评测，让教务问答更稳定，也让管理过程更可追踪。
              </Typography.Paragraph>
              <Space direction="vertical" size={8} style={{ width: "100%" }}>
                <Typography.Text className="login-selling-point">
                  <span className="login-point-dot" />
                  回答自动附带证据片段与来源定位
                </Typography.Text>
                <Typography.Text className="login-selling-point">
                  <span className="login-point-dot" />
                  支持知识库权限与角色分级访问
                </Typography.Text>
                <Typography.Text className="login-selling-point">
                  <span className="login-point-dot" />
                  评测与监控闭环，便于持续优化质量
                </Typography.Text>
              </Space>
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={12} className="login-form-col">
          <Card className="card-soft login-form-card">
            <Typography.Title level={3} className="login-form-title">
              账号登录
            </Typography.Title>
            <Typography.Paragraph className="login-form-subtitle">
              登录后可使用会话历史、反馈回放与管理能力。
            </Typography.Paragraph>
            <Form<LoginFormValues>
              form={form}
              layout="vertical"
              onFinish={async (values) => {
                setSubmitting(true);
                try {
                  await signIn(values);
                  message.success("登录成功");
                  navigate(nextPath, { replace: true });
                } catch (error) {
                  const normalized = normalizeApiError(error);
                  message.error(formatApiErrorMessage(normalized));
                } finally {
                  setSubmitting(false);
                }
              }}
            >
              <Form.Item
                name="email"
                label="邮箱"
                rules={[
                  { required: true, message: "请输入邮箱" },
                  { type: "email", message: "邮箱格式不正确" }
                ]}
              >
                <Input placeholder="admin@example.com" autoComplete="username" />
              </Form.Item>
              <Form.Item
                name="password"
                label="密码"
                rules={[{ required: true, message: "请输入密码" }]}
              >
                <Input.Password placeholder="请输入密码" autoComplete="current-password" />
              </Form.Item>
              <Form.Item style={{ marginBottom: 8 }}>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={submitting}
                  block
                  className="login-primary-button"
                >
                  登录
                </Button>
              </Form.Item>
            </Form>

            <Button
              type="link"
              className="login-anonymous-entry"
              onClick={() => {
                navigate("/app/ask");
              }}
            >
              继续匿名问答
            </Button>

            {isDev ? (
              <Typography.Text className="login-dev-hint">
                开发环境提示：若登录失败，请确认后端已启动且本地代理配置正确。
              </Typography.Text>
            ) : null}
          </Card>
        </Col>
      </Row>
    </div>
  );
}

