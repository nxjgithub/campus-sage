"""SearxNG 健康检查和性能测试脚本。

用于验证 SearxNG 配置是否正确，以及各搜索引擎的可用性。
"""

import sys
import time
from pathlib import Path

import httpx

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.settings import get_settings  # noqa: E402


def check_searxng_health(base_url: str, timeout: int = 10) -> bool:
    """测试 SearxNG HTTP 服务是否可达。"""

    print(f"\n🔍 测试 SearxNG 连通性: {base_url}")
    try:
        response = httpx.get(
            f"{base_url}/healthz",
            timeout=timeout,
            trust_env=False,
        )
        if response.status_code >= 500:
            print(f"❌ SearxNG HTTP 服务异常: {response.status_code}")
            return False
        print(f"✅ SearxNG HTTP 服务可达 (状态码 {response.status_code})")
        return True
    except Exception as e:
        print(f"❌ SearxNG 连接失败: {e}")
        return False


def check_search_engines(base_url: str, query: str = "site:example.com test") -> dict:
    """测试各个搜索引擎的响应情况。"""

    print(f"\n🧪 测试搜索引擎响应: '{query}'")
    engines_status = {}

    try:
        response = httpx.get(
            f"{base_url}/search",
            params={"q": query, "format": "json"},
            timeout=10,
            trust_env=False,
        )
        if response.status_code != 200:
            print(f"❌ 搜索请求失败: {response.status_code}")
            print("   搜索上游当前不可用，CampusSage 将回退授权入口页抓取。")
            return engines_status

        data = response.json()
        results = data.get("results", [])
        print(f"📊 总共返回 {len(results)} 条结果")

        # 统计各引擎贡献的结果数
        for result in results:
            engine = result.get("engine", "unknown")
            engines_status[engine] = engines_status.get(engine, 0) + 1

        if engines_status:
            print("\n📈 各引擎贡献:")
            for engine, count in sorted(engines_status.items(), key=lambda x: x[1], reverse=True):
                status_icon = "✅" if count > 0 else "⚠️"
                print(f"  {status_icon} {engine}: {count} 条结果")
        else:
            print("⚠️ 未获取到任何搜索结果")

    except Exception as e:
        print(f"❌ 测试失败: {e}")

    return engines_status


def check_rate_limiting(base_url: str, num_requests: int = 5) -> float:
    """测试速率限制情况。"""

    print(f"\n⏱️  测试速率限制 (连续 {num_requests} 次请求)")
    start_time = time.time()
    success_count = 0
    error_count = 0

    for i in range(num_requests):
        try:
            response = httpx.get(
                f"{base_url}/search",
                params={"q": f"test {i}", "format": "json"},
                timeout=5,
                trust_env=False,
            )
            if response.status_code == 200:
                success_count += 1
            else:
                error_count += 1
                print(f"  请求 {i+1}: ❌ 状态码 {response.status_code}")
        except Exception as e:
            error_count += 1
            print(f"  请求 {i+1}: ❌ {str(e)[:50]}")

        # 短暂延迟，模拟真实使用场景
        time.sleep(0.5)

    elapsed = time.time() - start_time
    print("\n📊 测试结果:")
    print(f"  ✅ 成功: {success_count}/{num_requests}")
    print(f"  ❌ 失败: {error_count}/{num_requests}")
    print(f"  ⏱️  总耗时: {elapsed:.2f} 秒")
    print(f"  📈 平均每次请求: {elapsed/num_requests:.2f} 秒")

    return success_count / num_requests if num_requests > 0 else 0


def main():
    """主函数。"""

    settings = get_settings()
    base_url = settings.rag_web_search_base_url or "http://127.0.0.1:8082"

    print("=" * 60)
    print("CampusSage SearxNG 健康检查工具")
    print("=" * 60)
    print(f"SearxNG 地址: {base_url}")
    print(f"搜索提供商: {settings.rag_web_search_provider}")

    # 测试 1: 基本连通性
    is_healthy = check_searxng_health(base_url)
    if not is_healthy:
        print("\n❌ SearxNG HTTP 服务不可达，请检查服务是否启动")
        print("   运行命令: docker compose up -d searxng")
        sys.exit(1)

    # 测试 2: 搜索引擎响应
    engines_status = check_search_engines(
        base_url,
        query="site:jsj.suse.edu.cn 胡光忠 副校长"
    )

    # 测试 3: 速率限制
    success_rate = check_rate_limiting(base_url, num_requests=5)

    # 总结
    print("\n" + "=" * 60)
    print("📋 测试总结")
    print("=" * 60)

    if engines_status and success_rate >= 0.8:
        print("✅ SearxNG 配置良好，可以正常使用")
    elif success_rate >= 0.5:
        print("⚠️  SearxNG 部分可用，建议优化配置")
    else:
        print("❌ SearxNG 存在严重问题，需要修复")
        print("   说明：受控联网问答仍可回退授权入口页抓取，但搜索候选扩展暂不可用。")

    if not engines_status:
        print("\n💡 建议:")
        print("  1. 检查 deploy/searxng/settings.yml 中的引擎配置")
        print("  2. 确保启用了至少一个可用的搜索引擎")
        print("  3. 搜索结果持续为空时，配置其他可用引擎并保留入口页降级")
        print("  4. 重启 SearxNG 服务: docker compose restart searxng")

    print("\n🔗 相关配置文件:")
    print("  - SearxNG 配置: deploy/searxng/settings.yml")
    print("  - 环境变量: .env (RAG_WEB_SEARCH_*)")
    print("  - Docker 配置: docker-compose.yml")


if __name__ == "__main__":
    main()
