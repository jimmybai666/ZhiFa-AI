"""
缓存管理器 - 提升向量数据库查询性能

本模块提供内存缓存机制，用于缓存以下数据：
1. 法律分类列表
2. 罪名列表
3. 热门查询结果
4. 统计数据

特性：
- 带过期时间的 LRU 缓存
- 自动清理过期数据
- 线程安全
"""

import time
import threading
import json
from typing import Any, Optional, Dict
from collections import OrderedDict
from pathlib import Path


class CacheManager:
    """
    简单而高效的内存缓存管理器
    
    使用 OrderedDict 实现 LRU 缓存策略，支持自动过期清理。
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        """
        初始化缓存管理器
        
        Args:
            max_size: 最大缓存项数量（默认 1000）
            default_ttl: 默认过期时间（秒，默认 3600 = 1小时）
        """
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.lock = threading.RLock()  # 线程安全锁
        
        print(f"[缓存管理器] 已初始化 - 最大容量: {max_size}, 默认TTL: {default_ttl}秒")
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存的值，如果不存在或已过期则返回 None
        """
        with self.lock:
            if key not in self.cache:
                return None
            
            item = self.cache[key]
            
            # 检查是否过期
            if time.time() > item['expire_at']:
                del self.cache[key]
                return None
            
            # LRU: 将访问的项移到末尾
            self.cache.move_to_end(key)
            return item['value']
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 要缓存的值
            ttl: 过期时间（秒），如果为 None 则使用默认值
        """
        with self.lock:
            if ttl is None:
                ttl = self.default_ttl
            
            expire_at = time.time() + ttl
            
            # 如果已存在，先删除（更新顺序）
            if key in self.cache:
                del self.cache[key]
            
            # 添加新项
            self.cache[key] = {
                'value': value,
                'expire_at': expire_at
            }
            
            # 如果超过最大容量，删除最旧的项（LRU）
            while len(self.cache) > self.max_size:
                self.cache.popitem(last=False)
    
    def delete(self, key: str) -> None:
        """删除指定的缓存项"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
    
    def clear(self) -> None:
        """清空所有缓存"""
        with self.lock:
            self.cache.clear()
            print("[缓存管理器] 已清空所有缓存")
    
    def cleanup_expired(self) -> int:
        """
        清理所有过期的缓存项
        
        Returns:
            清理的项数
        """
        with self.lock:
            now = time.time()
            expired_keys = [
                key for key, item in self.cache.items()
                if now > item['expire_at']
            ]
            
            for key in expired_keys:
                del self.cache[key]
            
            if expired_keys:
                print(f"[缓存管理器] 已清理 {len(expired_keys)} 个过期项")
            
            return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            包含缓存统计的字典
        """
        with self.lock:
            return {
                'current_size': len(self.cache),
                'max_size': self.max_size,
                'usage_percent': round(len(self.cache) / self.max_size * 100, 2) if self.max_size > 0 else 0
            }


# 全局缓存实例
_global_cache: Optional[CacheManager] = None


def get_cache() -> CacheManager:
    """
    获取全局缓存管理器实例（单例模式）
    
    Returns:
        CacheManager 实例
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = CacheManager(
            max_size=1000,      # 最多缓存 1000 项
            default_ttl=1800    # 默认缓存 30 分钟
        )
    return _global_cache


def clear_cache() -> None:
    """清空全局缓存"""
    global _global_cache
    if _global_cache:
        _global_cache.clear()


# 定期清理过期缓存的后台任务
def start_cleanup_task(interval: int = 300):
    """
    启动定期清理过期缓存的后台任务
    
    Args:
        interval: 清理间隔（秒，默认 300 = 5分钟）
    """
    def cleanup_loop():
        while True:
            time.sleep(interval)
            cache = get_cache()
            cache.cleanup_expired()
    
    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()
    print(f"[缓存管理器] 后台清理任务已启动 - 间隔: {interval}秒")


# ==================== 系统设置和统计文件管理 ====================

# 获取项目根目录
_root_dir = Path(__file__).parent.parent.parent
SETTINGS_FILE = _root_dir / 'settings.json'
STATS_FILE = _root_dir / 'usage_stats.json'


def load_settings_file():
    """加载设置文件"""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def save_settings_file(settings):
    """保存设置文件"""
    safe_settings = settings.copy()
    if 'api_key' in safe_settings and safe_settings['api_key']:
        key = safe_settings['api_key']
        if len(key) > 8:
            safe_settings['api_key_masked'] = key[:4] + '****' + key[-4:]
        safe_settings['api_key'] = key
    
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(safe_settings, f, ensure_ascii=False, indent=2)


def load_stats_file():
    """加载使用统计"""
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {'qa_count': 0, 'contract_count': 0, 'case_count': 0}


def save_stats_file(stats):
    """保存使用统计"""
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def increment_stat(stat_type):
    """增加统计计数"""
    stats = load_stats_file()
    stats[stat_type] = stats.get(stat_type, 0) + 1
    save_stats_file(stats)

