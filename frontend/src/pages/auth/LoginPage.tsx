import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  Input,
  Row,
  Space,
  Typography,
  message
} from "antd";
import { useNavigate, useSearchParams } from "react-router-dom";
import { normalizeApiError } from "../../shared/api/errors";
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

  useEffect(() => {
    if (status !== "loading" && isAuthenticated) {
      navigate(nextPath, { replace: true });
    }
  }, [isAuthenticated, navigate, nextPath, status]);

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <Row gutter={[16, 16]} style={{ width: "100%", maxWidth: 980 }}>
        <Col xs={24} lg={11}>
          <Card className="hero-card">
            <Typography.Title level={3} style={{ marginTop: 0 }}>
              CampusSage
            </Typography.Title>
            <Typography.Paragraph className="hero-desc">
              登录后可访问会话历史、反馈回放、评测与管理员能力。未登录也可在公开知识库中进行匿名问答。
            </Typography.Paragraph>
            <Space direction="vertical" size={6}>
              <Typography.Text>• 引用可定位，支持证据卡片联动</Typography.Text>
              <Typography.Text>• 支持知识库权限与 RBAC 鉴权</Typography.Text>
              <Typography.Text>• 支持离线评测、队列监控与错误追踪</Typography.Text>
            </Space>
          </Card>
        </Col>
        <Col xs={24} lg={13}>
          <Card title="账号登录" className="card-soft">
            <Alert
              type="info"
              showIcon
              message="仅在后端已启动并配置好 CORS / 代理时可登录成功"
              style={{ marginBottom: 12 }}
            />
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
                  message.error(`${normalized.message}（${normalized.code}）`);
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
              <Space>
                <Button type="primary" htmlType="submit" loading={submitting}>
                  登录
                </Button>
                <Button
                  onClick={() => {
                    navigate("/app/ask");
                  }}
                >
                  匿名问答
                </Button>
              </Space>
            </Form>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
