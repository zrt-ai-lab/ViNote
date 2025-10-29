from anp.authentication import create_did_wba_document
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import json
from pathlib import Path

print("=" * 60)
print("生成服务端 DID 和密钥")
print("=" * 60)

# 1. 生成服务端 DID 文档
did_document, keys = create_did_wba_document(
    hostname="localhost",
    path_segments=["agent", "video-search"],
    agent_description_url="http://localhost:8000/ad.json"
)

# 保存服务端 DID 文档
did_dir = Path("./did_keys/video_search")
did_dir.mkdir(parents=True, exist_ok=True)

with open(did_dir / "did.json", 'w') as f:
    json.dump(did_document, f, indent=2)

# 保存服务端 DID 私钥
for method_fragment, (private_key_bytes, _) in keys.items():
    with open(did_dir / f"{method_fragment}_private.pem", 'wb') as f:
        f.write(private_key_bytes)

print(f"✓ 服务端 DID 生成完成: {did_document['id']}")
print(f"  保存位置: {did_dir}")

# 2. 生成服务端 JWT 密钥对
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key = private_key.public_key()

jwt_dir = Path("./jwt_keys/video_search")
jwt_dir.mkdir(parents=True, exist_ok=True)

private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)
with open(jwt_dir / "jwt_private_key.pem", 'wb') as f:
    f.write(private_pem)

public_pem = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)
with open(jwt_dir / "jwt_public_key.pem", 'wb') as f:
    f.write(public_pem)

print(f"✓ 服务端 JWT 密钥生成完成")
print(f"  保存位置: {jwt_dir}")

print("\n" + "=" * 60)
print("生成客户端 DID 和密钥")
print("=" * 60)

# 3. 生成客户端 DID 文档
client_did_document, client_keys = create_did_wba_document(
    hostname="localhost:9000",  # 注意端口号
    path_segments=["client", "video-search-client"],
    agent_description_url="http://localhost:9000/ad.json"
)

# 保存客户端 DID 文档
client_dir = Path("./client_did_keys")
client_dir.mkdir(parents=True, exist_ok=True)

with open(client_dir / "did.json", 'w') as f:
    json.dump(client_did_document, f, indent=2)

# 保存客户端 DID 私钥
for method_fragment, (private_key_bytes, _) in client_keys.items():
    with open(client_dir / f"{method_fragment}_private.pem", 'wb') as f:
        f.write(private_key_bytes)

print(f"✓ 客户端 DID 生成完成: {client_did_document['id']}")
print(f"  保存位置: {client_dir}")

print("\n" + "=" * 60)
print("✓ 所有密钥生成完成!")
print("=" * 60)