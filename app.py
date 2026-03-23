# -*- coding: utf-8 -*-
"""
火山方舟 Ark 视频生成 Web UI
基于 Gradio 构建的 Web 界面
"""

import os
import sys
import socket
import traceback

# 清除可能的代理设置，避免 Gradio 连接问题（502错误）
for var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'no_proxy', 'NO_PROXY', 'httpx_no_proxy', 'HTTPX_NO_PROXY']:
    os.environ.pop(var, None)
# 确保 httpx/requests 不走代理
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['HTTPX_NO_PROXY'] = 'localhost,127.0.0.1'

# 确保 Python stdout 使用 UTF-8 编码（Windows 兼容）
import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import gradio as gr
from gradio.components import Video

from config import (
    APP_TITLE,
    APP_DESCRIPTION,
    MODELS,
    MODEL_RESOLUTIONS,
    DURATIONS,
    RATIOS,
    API_KEY_ENV,
)
from api import ArkAPI, ArkAPIError


# ============================================================
# 全局状态
# ============================================================

# 当前任务状态
current_status = {"task_id": None, "status": None}


# ============================================================
# 核心功能函数
# ============================================================

def get_resolutions_for_model(model: str):
    """根据模型获取支持的分辨率列表"""
    return MODEL_RESOLUTIONS.get(model, ["720p"])


def mask_api_key(api_key: str) -> str:
    value = (api_key or "").strip()
    if not value:
        return "(empty)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def get_fallback_options(model: str, duration: int, resolution: str, ratio: str):
    options = [(model, duration, resolution, ratio)]
    candidates = [
        (model, duration, "720p", ratio),
        (model, 5, "720p", ratio),
        (model, 5, "720p", "16:9"),
        ("doubao-seedance-1-5-pro-251215", 5, "720p", "16:9"),
        ("doubao-seedance-1-0-pro-250118", 5, "720p", "16:9"),
    ]
    for item in candidates:
        if item not in options:
            options.append(item)
    return options


def encode_image_to_base64(image_path: str) -> str:
    """将图片文件转为 base64 格式"""
    import base64
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_format(image_path: str) -> str:
    """获取图片格式（小写）"""
    ext = os.path.splitext(image_path)[1].lower()
    format_map = {
        ".jpg": "jpeg",
        ".jpeg": "jpeg",
        ".png": "png",
        ".webp": "webp",
        ".bmp": "bmp",
        ".tiff": "tiff",
        ".gif": "gif",
    }
    return format_map.get(ext, "jpeg")


def create_video(api_key: str, model: str, prompt: str, duration: int,
                 resolution: str, ratio: str,
                 first_frame=None, last_frame=None, reference_images=None,
                 status_callback=None):
    """
    创建视频生成任务

    Args:
        api_key: API Key
        model: 模型名称
        prompt: 视频描述
        duration: 时长（秒）
        resolution: 分辨率
        ratio: 画面比例
        first_frame: 首帧图片文件路径（可选）
        last_frame: 尾帧图片文件路径（可选）
        reference_images: 参考图片文件路径列表（可选，1-4张）
        status_callback: 状态更新回调

    Yields:
        状态消息
    """
    import base64

    # 1. 验证输入
    if not api_key or not api_key.strip():
        yield "❌ 错误：请输入 API Key", None, None
        return

    if not prompt or not prompt.strip():
        yield "❌ 错误：请输入视频描述", None, None
        return

    # 2. 处理首帧图片
    first_frame_url = None
    if first_frame and isinstance(first_frame, str) and os.path.exists(first_frame):
        try:
            img_format = get_image_format(first_frame)
            img_base64 = encode_image_to_base64(first_frame)
            first_frame_url = f"data:image/{img_format};base64,{img_base64}"
        except Exception as e:
            yield f"❌ 首帧图片读取失败: {str(e)}", None, None
            return

    # 3. 处理尾帧图片
    last_frame_url = None
    if last_frame and isinstance(last_frame, str) and os.path.exists(last_frame):
        try:
            img_format = get_image_format(last_frame)
            img_base64 = encode_image_to_base64(last_frame)
            last_frame_url = f"data:image/{img_format};base64,{img_base64}"
        except Exception as e:
            yield f"❌ 尾帧图片读取失败: {str(e)}", None, None
            return

    # 4. 处理参考图片（支持1-4张）
    reference_image_urls = []
    if reference_images:
        # reference_images 可能是文件路径列表，也可能是单个文件路径
        if isinstance(reference_images, str):
            # 单个文件路径转为列表
            reference_images = [reference_images]
        elif not isinstance(reference_images, (list, tuple)):
            reference_images = list(reference_images) if reference_images else []

        # 限制最多4张
        if len(reference_images) > 4:
            yield "❌ 参考图片最多支持4张，请减少图片数量", None, None
            return

        for ref_path in reference_images:
            if not ref_path or not isinstance(ref_path, str):
                continue
            if not os.path.exists(ref_path):
                continue
            try:
                img_format = get_image_format(ref_path)
                img_base64 = encode_image_to_base64(ref_path)
                reference_image_urls.append(f"data:image/{img_format};base64,{img_base64}")
            except Exception as e:
                yield f"❌ 参考图片读取失败: {str(e)}", None, None
                return

    yield "🚀 正在创建视频生成任务...", None, None

    try:
        print(f"[DEBUG] API Key: {mask_api_key(api_key)}")
        api = ArkAPI(api_key)
        duration_value = int(duration)
        task_id = None
        selected_model = model
        selected_duration = duration_value
        selected_resolution = resolution
        selected_ratio = ratio
        fallback_options = get_fallback_options(model, duration_value, resolution, ratio)

        for idx, (candidate_model, candidate_duration, candidate_resolution, candidate_ratio) in enumerate(
            fallback_options
        ):
            try:
                task_id = api.create_video_task(
                    model=candidate_model,
                    prompt=prompt.strip(),
                    duration=candidate_duration,
                    resolution=candidate_resolution,
                    ratio=candidate_ratio,
                    first_frame_url=first_frame_url,
                    last_frame_url=last_frame_url,
                    reference_images=reference_image_urls if reference_image_urls else None,
                )
                selected_model = candidate_model
                selected_duration = candidate_duration
                selected_resolution = candidate_resolution
                selected_ratio = candidate_ratio
                break
            except ArkAPIError as e:
                # 火山方舟 API 错误码处理
                error_code = str(e.code) if e.code else ""
                if error_code in ("2061", "40001", "40002") and idx < len(fallback_options) - 1:
                    yield f"⚠️ 套餐不支持 {candidate_model}-{candidate_duration}s-{candidate_resolution}-{candidate_ratio}，正在尝试兼容组合...", None, None
                    continue
                raise

        if not task_id:
            raise ArkAPIError("创建任务失败：未获取到 task_id")

        if (selected_model, selected_duration, selected_resolution, selected_ratio) != (model, duration_value, resolution, ratio):
            yield (
                f"✅ 已自动切换到兼容配置：{selected_model}-{selected_duration}s-{selected_resolution}-{selected_ratio}\n"
                f"↪️ 原始配置：{model}-{duration_value}s-{resolution}-{ratio}"
            ), None, None

        current_status["task_id"] = task_id
        yield f"📋 任务已创建，ID: {task_id}\n⏳ 等待视频生成中...", None, None

        # 4. 轮询等待完成
        def on_status_change(status: str, elapsed: float):
            current_status["status"] = status
            msg = f"⏳ 状态: {status} (已等待 {int(elapsed)} 秒)"
            if status_callback:
                status_callback(msg)

        result = api.wait_for_completion(
            task_id=task_id,
            callback=on_status_change,
        )

        # 5. 返回结果
        video_url = result["video_url"]
        yield f"✅ 视频生成成功！\n🔗 下载链接已获取", video_url, video_url

    except ArkAPIError as e:
        yield f"❌ API 错误: {str(e)}", None, None
    except ValueError:
        yield "❌ 参数错误：视频时长必须是数字", None, None
    except Exception as e:
        yield f"❌ 未知错误: {str(e)}", None, None


def test_api_connection(api_key: str):
    if not api_key or not api_key.strip():
        return "❌ 请先输入 API Key"
    try:
        print(f"[DEBUG] API Key: {mask_api_key(api_key)}")
        api = ArkAPI(api_key)
        # 用一个无效 task_id 测试连接，返回 404 属正常
        result = api.query_task_status("connectivity-test-task")
        status = result.get("status")
        description = result.get("description")
        if status and status != "Unknown":
            return f"✅ 连接成功：Token 可用，接口可访问（返回状态: {status}）"
        if description:
            return f"✅ 连接成功：接口已响应（返回信息: {description}）"
        return "✅ 连接成功：已访问到视频接口"
    except ArkAPIError as e:
        if e.status_code in (401, 403):
            return f"❌ 鉴权失败：{str(e)}"
        return f"❌ 连接失败：{str(e)}"
    except Exception as e:
        return f"❌ 连接失败：{str(e)}"


def update_resolutions(model: str):
    """更新分辨率下拉选项"""
    resolutions = get_resolutions_for_model(model)
    return gr.update(choices=resolutions, value=resolutions[0])


# ============================================================
# 任务列表功能
# ============================================================

def load_task_list(api_key: str, status_filter: str, page_size: int = 50):
    """加载任务列表"""
    if not api_key or not api_key.strip():
        return "<div style='color:#E8630A;padding:20px;'>⚠️ 请先在左侧输入 API Key</div>", ""

    try:
        api = ArkAPI(api_key)
        # 中文状态 → API 英文状态
        status_map = {
            "排队中": "queued",
            "运行中": "running",
            "成功": "succeeded",
            "失败": "failed",
            "已过期": "expired",
        }
        status = status_map.get(status_filter) if status_filter and status_filter != "全部" else None
        result = api.list_tasks(page_num=1, page_size=page_size, status=status)
        items = result.get("items", [])
        total = result.get("total", 0)

        if not items:
            return f"<div style='padding:20px;'>📭 暂无任务记录（总计 {total} 条）</div>", f"共 {total} 条任务"

        # 状态映射
        status_map = {
            "queued": "⏳ 排队中",
            "running": "🔄 生成中",
            "succeeded": "✅ 成功",
            "failed": "❌ 失败",
            "expired": "⏰ 已过期",
        }

        rows = []
        for item in items:
            tid = item.get("id", "")
            model_name = item.get("model", "")
            status_val = item.get("status", "")
            status_label = status_map.get(status_val, status_val)
            created = item.get("created_at", "")
            # 提取视频URL（如果有）
            content = item.get("content", {})
            video_url = ""
            if isinstance(content, dict):
                video_url = content.get("video_url", "")

            status_color = {
                "queued": "#FFA500",
                "running": "#1E90FF",
                "succeeded": "#28a745",
                "failed": "#dc3545",
                "expired": "#6c757d",
            }.get(status_val, "#666")

            # 查看按钮：直接在新标签页打开详情（构造方舟任务详情页）
            # 如果有视频链接，直接显示下载链接
            if video_url:
                view_btn = f"<a href='{video_url}' target='_blank' style='background:#E8630A;color:white;padding:4px 10px;border-radius:6px;text-decoration:none;font-size:13px;'>⬇️ 下载视频</a>"
            else:
                view_btn = f"<span style='color:#999;font-size:13px;'>-</span>"

            rows.append(f"""<tr>
                <td style='max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' title='{tid}'>{tid}</td>
                <td style='font-size:12px;'>{model_name}</td>
                <td><span style='background:{status_color}20;color:{status_color};padding:3px 8px;border-radius:12px;font-size:12px;'>{status_label}</span></td>
                <td style='font-size:12px;color:#666;'>{created}</td>
                <td>{view_btn}</td>
            </tr>""")

        table_html = f"""
        <div style='margin-bottom:10px;color:#666;'>共 {total} 条任务</div>
        <div style='overflow-x:auto;border:1px solid #eee;border-radius:10px;'>
        <table style='width:100%;border-collapse:collapse;font-size:14px;'>
            <thead>
                <tr style='background:#f8f4f0;'>
                    <th style='padding:10px 8px;text-align:left;'>任务ID</th>
                    <th style='padding:10px 8px;text-align:left;'>模型</th>
                    <th style='padding:10px 8px;text-align:left;'>状态</th>
                    <th style='padding:10px 8px;text-align:left;'>创建时间</th>
                    <th style='padding:10px 8px;text-align:left;'>操作</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>
        </div>
        """
        return table_html, f"✅ 已加载 {len(items)} 条（总计 {total} 条）"

    except ArkAPIError as e:
        return f"<div style='color:#dc3545;padding:20px;'>❌ API 错误: {str(e)}</div>", ""
    except Exception as e:
        return f"<div style='color:#dc3545;padding:20px;'>❌ 加载失败: {str(e)}</div>", ""


# ============================================================
# UI 布局
# ============================================================

def build_ui():
    """构建 Gradio UI"""

    # 自定义 CSS 样式
    custom_css = """
    .main-header {
        text-align: center;
        padding: 20px 0;
    }
    .status-box {
        background: linear-gradient(90deg, #e8630a 0%, #ff6b35 100%);
        padding: 15px;
        border-radius: 10px;
        color: white;
        font-weight: bold;
    }
    .info-box {
        background: #fff4ed;
        padding: 15px;
        border-radius: 10px;
        border-left: 4px solid #E8630A;
    }
    """

    with gr.Blocks(
        title=APP_TITLE,
        css=custom_css,
        theme=gr.themes.Soft(
            primary_hue="orange",
            secondary_hue="red",
        )
    ) as demo:

        # ---------- 标签页 ----------
        with gr.Tabs():
            with gr.Tab("🎬 视频生成"):
                # ---------- 标题区域 ----------
                gr.Markdown(f"# {APP_TITLE}")
                gr.Markdown(APP_DESCRIPTION)

                with gr.Row():
                    with gr.Column(scale=3):
                        # ---------- 主输入区域 ----------
                        with gr.Group():
                            gr.Markdown("### 🔑 API 设置")

                            api_key_input = gr.Textbox(
                                label="API Key",
                                placeholder=f"请输入火山方舟 Ark API Key（也可设置环境变量 {API_KEY_ENV}）",
                                type="password",
                                value=os.environ.get(API_KEY_ENV, ""),
                            )

                        with gr.Group():
                            gr.Markdown("### 🎬 生成设置")

                            with gr.Row():
                                model_dropdown = gr.Dropdown(
                                    choices=MODELS,
                                    value="doubao-seedance-1-5-pro-251215",
                                    label="选择模型",
                                    info="不同模型效果和速度可能不同",
                                )

                                duration_radio = gr.Radio(
                                    choices=[str(d) for d in DURATIONS],
                                    value="5",
                                    label="视频时长",
                                    info="生成视频的时长（秒）",
                                )

                            with gr.Row():
                                resolution_dropdown = gr.Dropdown(
                                    choices=["480p", "720p", "1080p"],
                                    value="720p",
                                    label="分辨率",
                                )

                                ratio_dropdown = gr.Dropdown(
                                    choices=RATIOS,
                                    value="16:9",
                                    label="画面比例",
                                    info="视频画面宽高比",
                                )

                            with gr.Row():
                                first_frame_input = gr.Image(
                                    type="filepath",
                                    label="🖼️ 首帧图片（可选）",
                                    height=80,
                                )
                                last_frame_input = gr.Image(
                                    type="filepath",
                                    label="🖼️ 尾帧图片（可选）",
                                    height=80,
                                )

                            reference_images_input = gr.File(
                                file_count="multiple",
                                label="🖼️ 参考图片（1-4张，仅 Seedance 1.0 lite i2v 支持）",
                                file_types=["image"],
                                height=80,
                            )

                            prompt_textbox = gr.Textbox(
                                label="✏️ 视频描述 (Prompt)",
                                placeholder="描述你想要生成的视频内容，例如：一只橘色的猫咪在阳光下打盹，背景是花园...",
                                lines=4,
                                info="详细的描述有助于生成更好的效果",
                            )

                        # ---------- 生成按钮 ----------
                        with gr.Row():
                            generate_btn = gr.Button(
                                "🎬 开始生成视频",
                                variant="primary",
                                size="lg",
                            )
                            test_connection_btn = gr.Button("🔍 测试 API 连接", size="sm")

                    with gr.Column(scale=2):
                        # ---------- 输出区域 ----------
                        with gr.Group():
                            gr.Markdown("### 📺 视频预览")

                            status_output = gr.Textbox(
                                label="生成状态",
                                lines=3,
                                interactive=False,
                                placeholder="点击生成按钮后将显示任务状态...",
                            )

                            video_output = gr.Video(
                                label="生成结果",
                                height=400,
                            )

                            download_link = gr.HTML(
                                label="下载链接",
                            )

                # ---------- 模型变化时更新分辨率 ----------
                model_dropdown.change(
                    fn=update_resolutions,
                    inputs=[model_dropdown],
                    outputs=[resolution_dropdown],
                )

                # ---------- 生成按钮点击事件 ----------
                generate_btn.click(
                    fn=create_video,
                    inputs=[
                        api_key_input,
                        model_dropdown,
                        prompt_textbox,
                        duration_radio,
                        resolution_dropdown,
                        ratio_dropdown,
                        first_frame_input,
                        last_frame_input,
                        reference_images_input,
                    ],
                    outputs=[
                        status_output,
                        video_output,
                        download_link,
                    ],
                )

                test_connection_btn.click(
                    fn=test_api_connection,
                    inputs=[api_key_input],
                    outputs=[status_output],
                )

                # ---------- 示例 ----------
                gr.Markdown("### 💡 使用示例")
                gr.Examples(
                    examples=[
                        ["一只可爱的小猫在草地上追蝴蝶，阳光明媚，微风轻拂"],
                        ["海边的日落场景，金色的阳光洒在波光粼粼的海面上"],
                        ["一位宇航员在太空中漂浮，背景是璀璨的星空"],
                        ["城市夜景，霓虹灯闪烁，车流不息"],
                    ],
                    inputs=[prompt_textbox],
                    label="点击示例快速体验",
                )

                # ---------- 底部信息 ----------
                gr.Markdown("""
                ---
                ### 📌 使用说明

                1. **获取 API Key**: 前往 [火山方舟 Ark 开放平台](https://ark.cn-beijing.volces.com) 获取 API Key
                2. **输入 Key**: 在上方输入框填入您的 API Key
                3. **编写描述**: 输入您想要的视频内容描述，越详细效果越好
                4. **开始生成**: 点击「开始生成视频」按钮，等待片刻即可

                ### ⚠️ 注意事项

                - 视频生成可能需要 1-3 分钟，请耐心等待
                - 不同模型的生成速度和效果有所差异
                - 请确保您的 API Key 有足够的额度
                - 支持 2-12 秒视频生成，支持多种画面比例
                """)

            # ---------- 任务列表 Tab ----------
            with gr.Tab("📋 任务列表"):
                gr.Markdown("### 📋 任务列表")

                with gr.Row():
                    task_status_filter = gr.Dropdown(
                        choices=["全部", "排队中", "运行中", "成功", "失败", "已过期"],
                        value="全部",
                        label="状态筛选",
                        scale=2,
                    )
                    task_refresh_btn = gr.Button("🔄 刷新列表", variant="primary", scale=1)
                    task_count_output = gr.Textbox(label="状态", lines=1, scale=2)

                task_list_output = gr.HTML(label="任务列表")

                task_refresh_btn.click(
                    fn=load_task_list,
                    inputs=[api_key_input, task_status_filter],
                    outputs=[task_list_output, task_count_output],
                )
                task_status_filter.change(
                    fn=load_task_list,
                    inputs=[api_key_input, task_status_filter],
                    outputs=[task_list_output, task_count_output],
                )

    return demo


# ============================================================
# 入口
# ============================================================

def main():
    """主入口"""
    demo = build_ui()

    # 获取端口（支持环境变量配置）
    port = int(os.environ.get("GRADIO_PORT", 7860))

    print(f"""\
================================================
    火山方舟 Ark 视频生成 Web UI 启动中...
================================================
  访问地址: http://localhost:{port}
  API Host: https://ark.cn-beijing.volces.com
================================================
    """)

    host = "127.0.0.1"
    print("端口检测...", end="")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        in_use = sock.connect_ex((host, port)) == 0
    if in_use:
        print(f"端口 {port} 已被占用")
    else:
        print(f"端口 {port} 可用")

    try:
        demo.launch(
            server_name=host,
            server_port=port,
            share=False,
            inbrowser=False,
            show_error=True,
            prevent_thread_lock=False,
            max_threads=1,
        )
    except Exception:
        print("启动失败，详细日志如下：")
        print(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
