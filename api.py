# -*- coding: utf-8 -*-
"""
火山方舟 Ark API 调用封装
"""

import requests
import time
import json
from typing import Optional, Dict, Any, List
from config import API_HOST, POLL_INTERVAL, POLL_TIMEOUT


class ArkAPIError(Exception):
    """API 调用异常"""
    def __init__(self, message: str, code: Optional[str] = None, status_code: Optional[int] = None):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(self.message)

    def __str__(self):
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


class ArkAPI:
    """火山方舟 Ark API 封装类"""

    def __init__(self, api_key: str):
        """
        初始化 API 客户端

        Args:
            api_key: Ark API Key
        """
        if not api_key or not api_key.strip():
            raise ValueError("API Key 不能为空")

        self.api_key = api_key.strip()
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        发送 HTTP 请求

        Args:
            method: HTTP 方法
            endpoint: API 端点
            **kwargs: 其他 requests 参数

        Returns:
            响应 JSON 数据
        """
        url = f"{API_HOST}{endpoint}"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                **kwargs
            )

            # 尝试解析 JSON 响应
            try:
                data = response.json()
            except Exception:
                data = {"raw_text": response.text}

            # 检查 HTTP 状态码
            if response.status_code != 200:
                error_msg = data.get("error", {}).get("message", data.get("message", "未知错误"))
                raise ArkAPIError(
                    message=error_msg,
                    code=data.get("error", {}).get("code"),
                    status_code=response.status_code
                )

            return data

        except requests.exceptions.Timeout:
            raise ArkAPIError("请求超时，请检查网络连接")
        except requests.exceptions.ConnectionError:
            raise ArkAPIError("无法连接到 API 服务器，请检查网络")
        except requests.exceptions.RequestException as e:
            raise ArkAPIError(f"请求失败: {str(e)}")

    @staticmethod
    def _brief_response(data: Dict[str, Any], max_len: int = 300) -> str:
        try:
            text = json.dumps(data, ensure_ascii=False)
        except Exception:
            text = str(data)
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text

    def create_video_task(
        self,
        model: str,
        prompt: str,
        duration: int = 5,
        resolution: str = "720p",
        ratio: str = "16:9",
        first_frame_url: Optional[str] = None,
        last_frame_url: Optional[str] = None,
        reference_images: Optional[List[str]] = None,
        seed: int = -1,
        camera_fixed: bool = False,
        watermark: bool = True,
        generate_audio: bool = True,
        draft: bool = False,
        return_last_frame: bool = False,
    ) -> str:
        """
        创建视频生成任务

        Args:
            model: 模型名称
            prompt: 视频描述
            duration: 时长（秒），支持 2-12 秒
            resolution: 分辨率，支持 480p, 720p, 1080p
            ratio: 画面比例，支持 16:9, 4:3, 1:1, 3:4, 9:16, 21:9, adaptive
            first_frame_url: 首帧图片 URL（可选，用于图生视频）
            last_frame_url: 尾帧图片 URL（可选，用于首尾帧视频）
            reference_images: 参考图片 URL 列表（可选，1-4张，仅支持 Seedance 1.0 lite i2v）
            seed: 随机种子，-1 表示随机
            camera_fixed: 是否固定镜头
            watermark: 是否添加水印
            generate_audio: 是否生成音频
            draft: 是否草稿模式
            return_last_frame: 是否返回尾帧

        Returns:
            task_id: 任务 ID
        """
        content = [{"type": "text", "text": prompt}]

        # 如果有首帧图片，添加到 content 中
        if first_frame_url:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": first_frame_url,
                },
                "role": "first_frame",
            })

        # 如果有尾帧图片，添加到 content 中
        if last_frame_url:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": last_frame_url,
                },
                "role": "last_frame",
            })

        # 如果有参考图片，添加到 content 中（支持1-4张）
        if reference_images:
            for ref_url in reference_images:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": ref_url,
                    },
                    "role": "reference_image",
                })

        payload = {
            "model": model,
            "content": content,
            "resolution": resolution,
            "ratio": ratio,
            "duration": duration,
            "seed": seed,
            "camera_fixed": camera_fixed,
            "watermark": watermark,
            "generate_audio": generate_audio,
            "draft": draft,
            "return_last_frame": return_last_frame,
        }

        data = self._request("POST", "/api/v3/contents/generations/tasks", json=payload)

        task_id = data.get("id")
        if not task_id:
            response_preview = self._brief_response(data)
            raise ArkAPIError(f"创建任务失败：未获取到 task_id，响应: {response_preview}")

        return str(task_id)

    def query_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        查询任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务状态信息，包含 status, video_url 等字段
        """
        data = self._request("GET", f"/api/v3/contents/generations/tasks/{task_id}")

        # 火山方舟状态: queued, running, succeeded, failed, expired
        status = data.get("status", "Unknown")
        error_info = data.get("error")

        result = {
            "status": status,
            "task_id": data.get("id", task_id),
            "model": data.get("model"),
            "description": error_info.get("message") if error_info else None,
        }

        # 如果任务成功，提取视频 URL（从 content.video_url）
        if status == "succeeded":
            content = data.get("content", {})
            if isinstance(content, dict):
                result["video_url"] = content.get("video_url")
                result["last_frame_url"] = content.get("last_frame_url")

        return result

    def wait_for_completion(
        self,
        task_id: str,
        interval: int = POLL_INTERVAL,
        timeout: int = POLL_TIMEOUT,
        callback=None,
    ) -> Dict[str, Any]:
        """
        等待任务完成（轮询）

        Args:
            task_id: 任务 ID
            interval: 轮询间隔（秒）
            timeout: 超时时间（秒）
            callback: 状态回调函数，接收 (status, elapsed_time) 参数

        Returns:
            最终任务状态信息
        """
        start_time = time.time()
        last_status = None

        while True:
            elapsed = time.time() - start_time

            # 检查超时
            if elapsed > timeout:
                raise ArkAPIError(f"任务超时（{timeout}秒），请稍后重试")

            # 查询状态
            result = self.query_task_status(task_id)
            status = result["status"]

            # 状态变化时触发回调
            if status != last_status:
                last_status = status
                if callback:
                    callback(status, elapsed)

            # 检查是否完成
            if status == "succeeded":
                video_url = result.get("video_url")
                if not video_url:
                    raise ArkAPIError("任务成功但未获取到 video_url")
                return {
                    "status": "Success",
                    "video_url": video_url,
                    "task_id": task_id,
                }
            elif status == "failed":
                desc = result.get("description", "未知错误")
                raise ArkAPIError(f"任务失败: {desc}")
            elif status == "expired":
                raise ArkAPIError("任务已过期，请重新生成")

            # 等待后继续轮询
            time.sleep(interval)

    def list_tasks(
        self,
        page_num: int = 1,
        page_size: int = 10,
        status: Optional[str] = None,
        task_ids: Optional[List[str]] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        批量查询任务列表

        Returns:
            {"items": [...], "total": int}
        """
        url = f"{API_HOST}/api/v3/contents/generations/tasks"
        params = [("page_num", page_num), ("page_size", page_size)]
        if status:
            params.append(("filter.status", status))
        if task_ids:
            for tid in task_ids:
                params.append(("filter.task_ids", tid))
        if model:
            params.append(("filter.model", model))

        resp = requests.get(url, headers=self.headers, params=params)
        try:
            data = resp.json()
        except Exception:
            data = {"raw_text": resp.text}

        if resp.status_code != 200:
            error_msg = data.get("error", {}).get("message", data.get("message", "未知错误"))
            raise ArkAPIError(
                message=error_msg,
                code=data.get("error", {}).get("code"),
                status_code=resp.status_code,
            )

        items = data.get("items", [])
        total = data.get("total", len(items))
        return {"items": items, "total": total}

# -*- coding: utf-8 -*-
