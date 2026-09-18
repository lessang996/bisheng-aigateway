# 从 jose 库中导入 jwt 处理模块和异常捕获类
from jose import jwt, JWTError

# 这里填入你的 token 字符串
token = "eyJhbGciOiJIUzI1NiJ9.eyJqdGkiOiIzRFJBNjIBUHhoTSIsImV4cCI6MTc4OTQ3MjMzNSwidXNlck5vIjoiMDA1MDA3Iiwib3JnIjoi5Y2X5bk45pSv6KGM5Lia5Yqh6YOoIn0.bigLZf05Mduk2XwiNImXOlMAhcxLulsGurEIngbelvW8" 

# ⚠️ 必须使用生成该 token 时相同的密钥
SECRET_KEY = "bemk2ZfRbbm" 
ALGORITHM = "HS256"

try:
    # 解析并验证 Token
    # 注意：algorithms 参数是必须的，且必须与生成时使用的算法完全一致
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    
    print("Token 解析成功！")
    print("用户号 (userNo):", payload.get("userNo"))
    print("组织 (org):", payload.get("org"))
    print("完整载荷 (Payload):", payload)

# 异常捕获与处理
except JWTError:
    # Token 被篡改或签名无效
    print("Error: 无效的 Token，签名不匹配！")
except jwt.ExpiredSignatureError:
    # Token 已经过期
    print("Error: Token 已经过期！")
except Exception as e:
    # 其他未知异常
    print(f"发生未知错误: {e}")