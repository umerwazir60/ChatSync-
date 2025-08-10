from __future__ import annotations
import json, os, hashlib, time, uuid, shutil, base64
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple

DATA_DIR = os.path.join(os.getcwd(), 'data')
USERS_DIR = os.path.join(DATA_DIR, 'users')
CHATS_DIR = os.path.join(DATA_DIR, 'chats')
IMAGES_DIR = os.path.join(DATA_DIR, 'images')

def ensure_dirs() -> None:
    os.makedirs(USERS_DIR, exist_ok=True)
    os.makedirs(CHATS_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

# ---------- Helpers ----------

def _read_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default

def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

# ---------- Auth ----------

def _hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    if salt is None:
        salt = uuid.uuid4().hex
    digest = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return digest, salt

def user_path(username: str) -> str:
    safe = username.lower().strip()
    return os.path.join(USERS_DIR, f'{safe}.json')

@dataclass
class User:
    username: str
    password_hash: str
    salt: str
    created_at: float
    groups: List[str]

class Storage:
    def __init__(self):
        ensure_dirs()

    # Users
    def list_users(self) -> List[str]:
        users: List[str] = []
        if not os.path.exists(USERS_DIR):
            return users
        for fname in os.listdir(USERS_DIR):
            if fname.endswith('.json'):
                users.append(os.path.splitext(fname)[0])
        return sorted(users)

    def user_exists(self, username: str) -> bool:
        return os.path.exists(user_path(username))

    def create_user(self, username: str, password: str) -> Tuple[bool, str]:
        path = user_path(username)
        if os.path.exists(path):
            return False, 'Username already exists'
        pw_hash, salt = _hash_password(password)
        user = User(username=username, password_hash=pw_hash, salt=salt, created_at=time.time(), groups=[])
        _write_json(path, asdict(user))
        return True, 'User created'

    def verify_user(self, username: str, password: str) -> bool:
        data = _read_json(user_path(username), None)
        if not data:
            return False
        digest, _ = _hash_password(password, data['salt'])
        return digest == data['password_hash']

    def get_user(self, username: str) -> Optional[User]:
        data = _read_json(user_path(username), None)
        if not data:
            return None
        return User(**data)

    # Chats
    def _chat_file(self, chat_id: str) -> str:
        return os.path.join(CHATS_DIR, f'{chat_id}.json')

    def create_private_chat(self, user_a: str, user_b: str) -> str:
        ids = sorted([user_a.lower(), user_b.lower()])
        chat_id = 'dm_' + hashlib.md5(('|'.join(ids)).encode('utf-8')).hexdigest()
        path = self._chat_file(chat_id)
        if not os.path.exists(path):
            meta = {
                'chat_id': chat_id,
                'type': 'dm',
                'participants': ids,
                'created_at': time.time(),
                'messages': []
            }
            _write_json(path, meta)
        return chat_id

    def create_group_chat(self, name: str, participants: List[str]) -> str:
        chat_id = 'grp_' + uuid.uuid4().hex[:12]
        path = self._chat_file(chat_id)
        meta = {
            'chat_id': chat_id,
            'type': 'group',
            'name': name,
            'participants': sorted([p.lower() for p in participants]),
            'created_at': time.time(),
            'messages': []
        }
        _write_json(path, meta)
        return chat_id

    def list_user_chats(self, username: str) -> List[Dict]:
        items = []
        for fname in os.listdir(CHATS_DIR):
            if not fname.endswith('.json'):
                continue
            path = os.path.join(CHATS_DIR, fname)
            chat = _read_json(path, None)
            if not chat:
                continue
            if username.lower() in chat.get('participants', []):
                items.append({
                    'chat_id': chat['chat_id'],
                    'type': chat['type'],
                    'name': chat.get('name'),
                    'participants': chat['participants']
                })
        return sorted(items, key=lambda x: x['chat_id'])

    def get_chat(self, chat_id: str) -> Optional[Dict]:
        return _read_json(self._chat_file(chat_id), None)

    def append_message(self, chat_id: str, sender: str, text: Optional[str], image_path: Optional[str]) -> Dict:
        chat = self.get_chat(chat_id)
        if not chat:
            raise ValueError('Chat not found')
        message = {
            'id': uuid.uuid4().hex,
            'sender': sender.lower(),
            'text': text,
            'image': image_path,
            'ts': time.time()
        }
        chat['messages'].append(message)
        _write_json(self._chat_file(chat_id), chat)
        return message

    # Images
    def save_image_bytes(self, raw_bytes: bytes, ext: str) -> str:
        ext = ext.lower().strip('. ')
        if ext not in {'png','jpg','jpeg','gif','webp'}:
            ext = 'png'
        img_id = uuid.uuid4().hex[:16] + '.' + ext
        path = os.path.join(IMAGES_DIR, img_id)
        with open(path, 'wb') as f:
            f.write(raw_bytes)
        return path

    def image_to_data_url(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower().lstrip('.') or 'png'
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        return f'data:image/{ext};base64,{b64}'
