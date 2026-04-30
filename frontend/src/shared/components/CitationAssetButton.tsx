import { FileImageOutlined } from "@ant-design/icons";
import { Alert, Button, Image, Modal, Skeleton, Space, Typography } from "antd";
import { useEffect, useState } from "react";
import { apiClient } from "../api/client";

interface CitationAssetButtonProps {
  assetUrl: string;
  label?: string | null;
}

export function CitationAssetButton({ assetUrl, label }: CitationAssetButtonProps) {
  const [open, setOpen] = useState(false);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    return () => {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [objectUrl]);

  const handleOpen = async () => {
    setOpen(true);
    if (objectUrl || loading) {
      return;
    }
    setLoading(true);
    setFailed(false);
    try {
      const response = await apiClient.get<Blob>(normalizeAssetPath(assetUrl), {
        responseType: "blob"
      });
      setObjectUrl(URL.createObjectURL(response.data));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Button size="small" icon={<FileImageOutlined />} onClick={() => void handleOpen()}>
        查看原图
      </Button>
      <Modal
        title={label || "图片证据"}
        open={open}
        footer={null}
        width={820}
        destroyOnHidden
        onCancel={() => setOpen(false)}
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Typography.Text type="secondary">{label || "图片资产"}</Typography.Text>
          {loading ? <Skeleton.Image active style={{ width: "100%", height: 360 }} /> : null}
          {failed ? <Alert type="error" showIcon message="图片加载失败，请稍后重试" /> : null}
          {objectUrl ? (
            <Image
              src={objectUrl}
              alt={label || "图片证据"}
              style={{ maxHeight: 520, objectFit: "contain", width: "100%" }}
            />
          ) : null}
        </Space>
      </Modal>
    </>
  );
}

function normalizeAssetPath(assetUrl: string) {
  if (assetUrl.startsWith("/api/v1")) {
    return assetUrl.replace("/api/v1", "") || "/";
  }
  if (assetUrl.startsWith("http://") || assetUrl.startsWith("https://")) {
    const parsed = new URL(assetUrl);
    return parsed.pathname.replace("/api/v1", "") || "/";
  }
  return assetUrl;
}
