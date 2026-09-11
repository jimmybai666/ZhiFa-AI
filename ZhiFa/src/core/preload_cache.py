"""
缓存预加载工具 - 在服务启动时预热缓存

本模块提供缓存预加载功能，在服务启动时提前加载热门数据到缓存中，
从而提升首次访问的响应速度。

功能：
1. 预加载法律分类列表
2. 预加载罪名列表
3. 预加载案例统计数据
4. 预加载热门查询结果
"""

import time
from collections import Counter
import re
import os
from typing import Dict, Any

from ..vectorstore.utils import get_vectorstore
from .cache_manager import get_cache


def preload_law_categories() -> bool:
    """
    预加载法律分类列表到缓存
    
    Returns:
        bool: 预加载是否成功
    """
    try:
        print("[预加载] 正在加载法律分类列表...")
        start_time = time.time()
        
        cache = get_cache()
        cache_key = "law_categories"
        
        # 检查是否已缓存
        if cache.get(cache_key) is not None:
            print("[预加载] 法律分类列表已存在缓存中，跳过")
            return True
        
        vs = get_vectorstore("law")
        collection = vs._collection
        results = collection.get(include=["metadatas"])
        
        # 统计每个法律来源的文档数
        category_count = Counter()
        for metadata in results.get("metadatas", []):
            if metadata and "source" in metadata:
                source = metadata["source"]
                parts = source.replace("\\", "/").split("/")
                for i, part in enumerate(parts):
                    if "Law-Book" in part and i + 1 < len(parts):
                        category_folder = parts[i + 1]
                        category_name = re.sub(r'^\d+-', '', category_folder)
                        category_count[category_name] += 1
                        break
        
        categories = [
            {"name": name, "count": count}
            for name, count in category_count.most_common()
        ]
        
        # 缓存结果
        cache.set(cache_key, categories, ttl=3600)
        
        elapsed = time.time() - start_time
        print(f"[预加载] ✓ 法律分类列表已缓存 ({len(categories)} 个分类, 耗时 {elapsed:.2f}秒)")
        return True
        
    except Exception as e:
        print(f"[预加载] ✗ 法律分类列表预加载失败: {e}")
        return False


def preload_case_accusations() -> bool:
    """
    预加载罪名列表到缓存
    
    Returns:
        bool: 预加载是否成功
    """
    try:
        print("[预加载] 正在加载罪名列表...")
        start_time = time.time()
        
        cache = get_cache()
        cache_key = "case_accusations"
        
        # 检查是否已缓存
        if cache.get(cache_key) is not None:
            print("[预加载] 罪名列表已存在缓存中，跳过")
            return True
        
        vs = get_vectorstore("criminal_cases")
        collection = vs._collection
        results = collection.get(include=["metadatas"])
        
        # 统计每个罪名的案例数
        accusation_count = Counter()
        for metadata in results.get("metadatas", []):
            if metadata and "accusation" in metadata:
                accusation_str = metadata["accusation"]
                if accusation_str:
                    for acc in re.split(r'、(?![^[]*\])', accusation_str):
                        acc = acc.strip()
                        if acc:
                            accusation_count[acc] += 1
        
        accusations = [
            {"name": name, "count": count}
            for name, count in accusation_count.most_common()
        ]
        
        # 缓存结果
        cache.set(cache_key, accusations, ttl=3600)
        
        elapsed = time.time() - start_time
        print(f"[预加载] ✓ 罪名列表已缓存 ({len(accusations)} 个罪名, 耗时 {elapsed:.2f}秒)")
        return True
        
    except Exception as e:
        print(f"[预加载] ✗ 罪名列表预加载失败: {e}")
        return False


def preload_case_stats() -> bool:
    """
    预加载案例统计数据到缓存
    
    Returns:
        bool: 预加载是否成功
    """
    try:
        print("[预加载] 正在加载案例统计数据...")
        start_time = time.time()
        
        cache = get_cache()
        cache_key = "case_stats"
        
        # 检查是否已缓存
        if cache.get(cache_key) is not None:
            print("[预加载] 案例统计数据已存在缓存中，跳过")
            return True
        
        vs = get_vectorstore("criminal_cases")
        collection = vs._collection
        results = collection.get(include=["metadatas"])
        
        # 定义刑期区间
        ranges = [
            {"range": "6个月以下", "min": 0, "max": 6, "count": 0},
            {"range": "6个月-1年", "min": 6, "max": 12, "count": 0},
            {"range": "1-3年", "min": 12, "max": 36, "count": 0},
            {"range": "3-5年", "min": 36, "max": 60, "count": 0},
            {"range": "5-10年", "min": 60, "max": 120, "count": 0},
            {"range": "10年以上", "min": 120, "max": 999, "count": 0},
            {"range": "无期徒刑", "min": -1, "max": -1, "count": 0},
            {"range": "死刑", "min": -2, "max": -2, "count": 0},
        ]
        
        total = 0
        for metadata in results.get("metadatas", []):
            if not metadata:
                continue
            total += 1
            
            if metadata.get("death_penalty"):
                ranges[7]["count"] += 1
            elif metadata.get("life_imprisonment"):
                ranges[6]["count"] += 1
            else:
                imprisonment = metadata.get("imprisonment", 0)
                for r in ranges[:6]:
                    if r["min"] <= imprisonment < r["max"]:
                        r["count"] += 1
                        break
        
        result = {
            "total_cases": total,
            "imprisonment_ranges": ranges
        }
        
        # 缓存结果
        cache.set(cache_key, result, ttl=3600)
        
        elapsed = time.time() - start_time
        print(f"[预加载] ✓ 案例统计数据已缓存 (共 {total} 个案例, 耗时 {elapsed:.2f}秒)")
        return True
        
    except Exception as e:
        print(f"[预加载] ✗ 案例统计数据预加载失败: {e}")
        return False


def preload_all_caches() -> Dict[str, bool]:
    """
    预加载所有热门数据到缓存
    
    Returns:
        Dict[str, bool]: 各项预加载的结果
    """
    print("\n" + "="*60)
    print("[缓存预加载] 开始预热缓存...")
    print("="*60)
    
    total_start = time.time()
    
    results = {
        "law_categories": preload_law_categories(),
        "case_accusations": preload_case_accusations(),
        "case_stats": preload_case_stats()
    }
    
    total_elapsed = time.time() - total_start
    success_count = sum(1 for v in results.values() if v)
    
    print("="*60)
    print(f"[缓存预加载] 完成 - 成功 {success_count}/{len(results)} 项, 总耗时 {total_elapsed:.2f}秒")
    print("="*60 + "\n")
    
    return results


if __name__ == "__main__":
    # 可以单独运行此脚本来预热缓存
    preload_all_caches()

