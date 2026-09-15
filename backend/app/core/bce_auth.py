# -*- coding: utf-8 -*-
"""
百度大模型安全护栏接口 - 鉴权签名生成
对应 Java 版 getTokens / sha256Hex 实现
"""
import hmac
import hashlib
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

UTF8 = "utf-8"
AUTH_VERSION = "bce-auth-v1"
EXPIRATION_IN_SECONDS = 1800   # 文档要求固定值


def sha256_hex(signing_key: str, string_to_sign: str) -> str:
    """
    HmacSHA256 签名，返回小写十六进制字符串
    对应 Java: sha256Hex(signingKey, stringToSign)

    :param signing_key:   密钥（字符串形式，注意第二次调用时传的是上一步的 hex 结果）
    :param string_to_sign: 待签名字符串
    :return: 64 位小写 hex 字符串
    """
    if not isinstance(signing_key, str) or not isinstance(string_to_sign, str):
        raise TypeError("signing_key and string_to_sign must be strings")
    return hmac.new(signing_key.encode(UTF8), string_to_sign.encode(UTF8), hashlib.sha256).hexdigest()


def get_tokens(ak: str, sk: str,
               expiration_in_seconds: int = EXPIRATION_IN_SECONDS,
               time_zone: Optional[str] = None) -> str:
    """
    生成 Authorization 请求头
    格式: bce-auth-v1/{ak}/{timestamp}/{expirationInSeconds}/host/{signature}

    :param ak:  Access Key（即 appkey）
    :param sk:  Secret Key
    :param expiration_in_seconds: 过期时间，固定 1800
    :param time_zone: 当前 Unix 时间戳（秒级字符串）
    :return: authorization header 字符串
    """
    if not ak or not sk:
        raise ValueError("ak and sk are required")
    if expiration_in_seconds != EXPIRATION_IN_SECONDS:
        raise ValueError("expiration_in_seconds must be 1800")
    if time_zone is None:
        time_zone = str(int(time.time()))
    if not str(time_zone).isdigit():
        raise ValueError("time_zone must be a Unix timestamp")

    # 1. 签名前缀
    auth_string_prefix = f"{AUTH_VERSION}/{ak}/{time_zone}/{expiration_in_seconds}"

    # 2. 规范化请求串: HTTP_METHOD + "\n" + URI + "\n" + CanonicalHeaders
    #    此处 URI 为空、header 为 "host:"（值为空）
    canonical_request = "POST" + "\n" + "\n" + "host:"

    # 3. 派生签名密钥（注意：key 是 sk 字符串本身）
    signing_key = sha256_hex(sk, auth_string_prefix)
    # 4. 计算最终签名（key 是上一步的 hex 字符串，而非其原始字节）
    signature = sha256_hex(signing_key, canonical_request)
    # 5. 拼接 Authorization
    return f"{auth_string_prefix}/host/{signature}"


def current_timestamp() -> str:
    """获取当前秒级时间戳字符串，URL 参数与签名必须使用同一个值"""
    return str(int(time.time()))
