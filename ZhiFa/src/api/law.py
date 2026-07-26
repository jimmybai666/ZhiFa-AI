"""
法律法规查询API模块
"""
from flask import request, jsonify
import traceback
import re
import os
from collections import Counter
from langchain_core.documents import Document

from ..vectorstore.utils import get_vectorstore
from ..core.cache_manager import get_cache


def register_law_routes(app):
    """注册法律法规查询相关路由"""
    
    @app.route('/api/laws/all', methods=['GET'])
    def get_all_laws():
        """
        获取所有法律法规数据（优化版 - 用于前端虚拟滚动）
        
        参数:
        - category: 可选，按分类筛选
        - lite: 可选，精简模式（只返回必要字段）
        
        返回:
        {
            "laws": [{"id": 1, "content": "...", "law_name": "...", "category": "..."}],
            "total": 21288
        }
        """
        try:
            category = request.args.get('category', '')
            lite_mode = request.args.get('lite', 'true').lower() == 'true'
            
            # 尝试从缓存获取
            cache = get_cache()
            cache_key = f"all_laws:{category}:{lite_mode}"
            cached_result = cache.get(cache_key)
            
            if cached_result is not None:
                print(f"[缓存命中] 全部法律数据: category={category}")
                return jsonify(cached_result)
            
            print(f"[缓存未命中] 正在加载全部法律数据...")
            vs = get_vectorstore("law")
            collection = vs._collection
            
            # 获取所有数据
            all_data = collection.get(include=["documents", "metadatas"])
            
            laws = []
            for idx, (doc, meta) in enumerate(zip(
                all_data.get("documents", []),
                all_data.get("metadatas", [])
            )):
                if not meta:
                    continue
                    
                source = meta.get("source", "")
                
                # 提取类别名和法律名
                category_name = ""
                law_name = os.path.basename(source).replace(".md", "") if source else "未知"
                parts = source.replace("\\", "/").split("/")
                for i, part in enumerate(parts):
                    if "Law-Book" in part and i + 1 < len(parts):
                        category_folder = parts[i + 1]
                        category_name = re.sub(r'^\d+-', '', category_folder)
                        break
                
                # 分类筛选
                if category and category not in category_name:
                    continue
                
                # 移除 HTML 注释（如 <!-- INFO END -->）
                content = re.sub(r'<!--.*?-->', '', doc, flags=re.DOTALL)
                content = content.strip()
                
                # 精简模式：限制内容长度
                if lite_mode and len(content) > 300:
                    content = content[:300] + "..."
                
                laws.append({
                    "id": idx,
                    "content": content,
                    "full_content": re.sub(r'<!--.*?-->', '', doc, flags=re.DOTALL).strip() if not lite_mode else None,
                    "law_name": law_name,
                    "category": category_name,
                    "source": source
                })
            
            result = {
                "laws": laws,
                "total": len(laws)
            }
            
            # 缓存结果（缓存30分钟）
            cache.set(cache_key, result, ttl=1800)
            print(f"[已缓存] 全部法律数据 ({len(laws)} 条)")
            
            return jsonify(result)
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/laws/<int:law_id>/detail', methods=['GET'])
    def get_law_detail(law_id):
        """
        获取单条法律法规的完整内容（延迟加载）
        
        参数:
        - law_id: 法律条目ID
        
        返回:
        {
            "id": 1,
            "content": "完整法条内容...",
            "law_name": "法律名称",
            "category": "分类"
        }
        """
        try:
            # 尝试从缓存获取
            cache = get_cache()
            cache_key = f"law_detail:{law_id}"
            cached_result = cache.get(cache_key)
            
            if cached_result is not None:
                print(f"[缓存命中] 法律详情: id={law_id}")
                return jsonify(cached_result)
            
            print(f"[缓存未命中] 正在加载法律详情: id={law_id}")
            vs = get_vectorstore("law")
            collection = vs._collection
            
            # 获取指定ID的数据
            all_data = collection.get(
                include=["documents", "metadatas"],
                offset=law_id,
                limit=1
            )
            
            if not all_data.get("documents"):
                return jsonify({"error": "未找到该法律条目"}), 404
            
            doc = all_data["documents"][0]
            meta = all_data["metadatas"][0] if all_data.get("metadatas") else {}
            
            source = meta.get("source", "")
            
            # 提取类别名和法律名
            category_name = ""
            law_name = os.path.basename(source).replace(".md", "") if source else "未知"
            parts = source.replace("\\", "/").split("/")
            for i, part in enumerate(parts):
                if "Law-Book" in part and i + 1 < len(parts):
                    category_folder = parts[i + 1]
                    category_name = re.sub(r'^\d+-', '', category_folder)
                    break
            
            # 尝试读取完整的原始法律文件
            full_content = None
            if source:
                # 构建完整的文件路径
                # source 可能是相对路径如 "data/Law-Book/..." 或绝对路径
                possible_paths = [
                    source,
                    os.path.join(os.getcwd(), source),
                    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), source)
                ]
                
                for path in possible_paths:
                    if os.path.exists(path):
                        try:
                            with open(path, 'r', encoding='utf-8') as f:
                                full_content = f.read()
                            print(f"[读取原始文件成功] {path}")
                            break
                        except Exception as e:
                            print(f"[读取文件失败] {path}: {e}")
            
            # 处理内容：移除 HTML 注释和 INFO END 标记
            if full_content:
                # 使用完整文件内容
                content = full_content
            else:
                content = doc
            
            # 移除 HTML 注释（如 <!-- INFO END -->）
            content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
            # 移除多余的空行
            content = re.sub(r'\n{3,}', '\n\n', content)
            content = content.strip()
            
            result = {
                "id": law_id,
                "content": content,
                "law_name": law_name,
                "category": category_name,
                "source": source
            }
            
            # 缓存结果（缓存1小时）
            cache.set(cache_key, result, ttl=3600)
            
            return jsonify(result)
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/laws/categories', methods=['GET'])
    def get_law_categories():
        """
        获取法律法规分类列表（带缓存优化）
        
        返回:
        {
            "categories": [{"name": "刑法", "count": 100}, ...]
        }
        """
        try:
            # 尝试从缓存获取
            cache = get_cache()
            cache_key = "law_categories"
            cached_result = cache.get(cache_key)
            
            if cached_result is not None:
                print("[缓存命中] 法律分类列表")
                return jsonify({"categories": cached_result, "cached": True})
            
            print("[缓存未命中] 正在加载法律分类列表...")
            vs = get_vectorstore("law")
            
            # 获取所有文档的source信息
            collection = vs._collection
            results = collection.get(include=["metadatas"])
            
            # 统计每个法律来源的文档数
            category_count = Counter()
            for metadata in results.get("metadatas", []):
                if metadata and "source" in metadata:
                    source = metadata["source"]
                    # 从路径提取法律名称，如 "data/Law-Book/7-刑法/刑法.md" -> "刑法"
                    parts = source.replace("\\", "/").split("/")
                    # 找到 Law-Book 后的部分
                    for i, part in enumerate(parts):
                        if "Law-Book" in part and i + 1 < len(parts):
                            # 获取类别文件夹名，如 "7-刑法"
                            category_folder = parts[i + 1]
                            # 提取类别名，如 "7-刑法" -> "刑法"
                            category_name = re.sub(r'^\d+-', '', category_folder)
                            category_count[category_name] += 1
                            break
            
            categories = [
                {"name": name, "count": count}
                for name, count in category_count.most_common()
            ]
            
            # 缓存结果（缓存1小时）
            cache.set(cache_key, categories, ttl=3600)
            print(f"[已缓存] 法律分类列表 ({len(categories)} 个分类)")
            
            return jsonify({"categories": categories})
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    
    @app.route('/api/laws/search', methods=['POST'])
    def search_laws():
        """
        搜索法律条文（优化版 - 支持缓存和智能分页）
        
        请求体:
        {
            "query": "搜索关键词",
            "category": "法律类别（可选）",
            "page": 1,
            "page_size": 20
        }
        
        返回:
        {
            "results": [{"content": "...", "source": "...", "category": "..."}],
            "total": 100,
            "page": 1,
            "page_size": 20
        }
        """
        try:
            data = request.get_json()
            query = data.get('query', '')
            category = data.get('category', '')
            page = data.get('page', 1)
            page_size = data.get('page_size', 20)
            
            # 构造缓存键
            cache = get_cache()
            cache_key = f"law_search:{query}:{category}:{page}:{page_size}"
            
            # 尝试从缓存获取
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                print(f"[缓存命中] 法律搜索: query={query}, category={category}, page={page}")
                return jsonify(cached_result)
            
            vs = get_vectorstore("law")
            
            if query:
                # 语义搜索（限制为合理的范围）
                search_k = min(200, page * page_size + 100)  # 动态调整搜索范围
                results = vs.similarity_search(query, k=search_k)
                
                # 过滤分类
                if category:
                    results = [
                        doc for doc in results
                        if category in doc.metadata.get("source", "")
                    ]
            else:
                # 无关键词时，使用智能批量加载策略
                collection = vs._collection
                
                # 计算需要的数据范围（避免一次性加载全部）
                # 只加载当前页和附近几页的数据
                buffer_pages = 3  # 缓冲页数
                offset = max(0, (page - buffer_pages) * page_size)
                limit = (buffer_pages * 2 + 1) * page_size
                
                # 使用 offset 和 limit 进行批量查询
                all_data = collection.get(
                    include=["documents", "metadatas"],
                    offset=offset,
                    limit=limit
                )
                
                results = []
                for i, (doc, meta) in enumerate(zip(
                    all_data.get("documents", []),
                    all_data.get("metadatas", [])
                )):
                    if category:
                        source = meta.get("source", "") if meta else ""
                        if category not in source:
                            continue
                    results.append(Document(page_content=doc, metadata=meta or {}))
                
                # 获取总数（使用缓存）
                total_cache_key = f"law_total:{category}"
                total = cache.get(total_cache_key)
                if total is None:
                    total = collection.count()
                    cache.set(total_cache_key, total, ttl=600)  # 缓存10分钟
            
            # 分页
            if query or not category:
                total = len(results)
            
            start = (page - 1) * page_size
            # 如果是批量加载，需要调整 start
            if not query:
                start = start - offset
            
            end = start + page_size
            paged_results = results[start:end] if start >= 0 else results[:page_size]
            
            # 格式化结果
            formatted = []
            for doc in paged_results:
                source = doc.metadata.get("source", "")
                # 提取类别名
                category_name = ""
                parts = source.replace("\\", "/").split("/")
                for i, part in enumerate(parts):
                    if "Law-Book" in part and i + 1 < len(parts):
                        category_folder = parts[i + 1]
                        category_name = re.sub(r'^\d+-', '', category_folder)
                        break
                
                # 提取法律名
                law_name = os.path.basename(source).replace(".md", "") if source else "未知"
                
                # 移除 HTML 注释（如 <!-- INFO END -->）
                content = re.sub(r'<!--.*?-->', '', doc.page_content, flags=re.DOTALL)
                content = content.strip()
                
                formatted.append({
                    "content": content,
                    "source": source,
                    "category": category_name,
                    "law_name": law_name
                })
            
            result = {
                "results": formatted,
                "total": total,
                "page": page,
                "page_size": page_size
            }
            
            # 缓存结果（缓存5分钟）
            cache.set(cache_key, result, ttl=300)
            
            return jsonify(result)
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    
    @app.route('/api/cases/accusations', methods=['GET'])
    def get_accusations():
        """
        获取所有罪名列表及统计（带缓存优化）
        
        返回:
        {
            "accusations": [{"name": "盗窃罪", "count": 1000}, ...]
        }
        """
        try:
            # 尝试从缓存获取
            cache = get_cache()
            cache_key = "case_accusations"
            cached_result = cache.get(cache_key)
            
            if cached_result is not None:
                print("[缓存命中] 罪名列表")
                return jsonify({"accusations": cached_result, "cached": True})
            
            print("[缓存未命中] 正在加载罪名列表...")
            vs = get_vectorstore("criminal_cases")
            collection = vs._collection
            results = collection.get(include=["metadatas"])
            
            # 统计每个罪名的案例数
            accusation_count = Counter()
            for metadata in results.get("metadatas", []):
                if metadata and "accusation" in metadata:
                    accusation_str = metadata["accusation"]
                    if accusation_str:
                        # 罪名可能是多个，用顿号分隔
                        # 但需跳过方括号内的顿号，如 [生产、销售]伪劣产品罪
                        for acc in re.split(r'、(?![^[]*\])', accusation_str):
                            acc = acc.strip()
                            if acc:
                                accusation_count[acc] += 1
            
            accusations = [
                {"name": name, "count": count}
                for name, count in accusation_count.most_common()
            ]
            
            # 缓存结果（缓存1小时）
            cache.set(cache_key, accusations, ttl=3600)
            print(f"[已缓存] 罪名列表 ({len(accusations)} 个罪名)")
            
            return jsonify({"accusations": accusations})
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    
    @app.route('/api/cases/all', methods=['GET'])
    def get_all_cases():
        """
        获取案例数据（分批加载版 - 用于前端虚拟滚动）
        
        参数:
        - batch: 批次号（从0开始）
        - batch_size: 每批数量（默认30000）
        - accusation: 可选，按罪名筛选
        
        返回:
        {
            "cases": [{...}],
            "total": 150000,
            "batch": 0,
            "has_more": true
        }
        """
        try:
            batch = int(request.args.get('batch', 0))
            batch_size = int(request.args.get('batch_size', 30000))
            accusation = request.args.get('accusation', '')
            
            # 尝试从缓存获取
            cache = get_cache()
            cache_key = f"all_cases_batch:{accusation}:{batch}:{batch_size}"
            cached_result = cache.get(cache_key)
            
            if cached_result is not None:
                print(f"[缓存命中] 案例批次加载 (batch={batch}, size={batch_size})")
                return jsonify(cached_result)
            
            print(f"[缓存未命中] 正在加载案例数据 (batch={batch}, size={batch_size})...")
            vs = get_vectorstore("criminal_cases")
            collection = vs._collection
            
            # 计算offset
            offset = batch * batch_size
            
            # 获取数据
            results = collection.get(
                include=["documents", "metadatas"],
                offset=offset,
                limit=batch_size
            )
            
            documents = results.get("documents", [])
            metadatas = results.get("metadatas", [])
            
            cases = []
            for idx, (doc, meta) in enumerate(zip(documents, metadatas)):
                if not meta:
                    continue
                
                # 按罪名筛选
                if accusation:
                    doc_acc = meta.get("accusation", "")
                    if accusation not in doc_acc:
                        continue
                
                # 计算真实的全局ID（offset + 当前索引）
                global_id = offset + idx
                
                # 精简模式：只返回必要字段
                case_data = {
                    "id": global_id,  # 添加全局唯一ID
                    "fact": doc[:200] if doc else "",  # 截断案情描述
                    "accusation": meta.get("accusation", ""),
                    "imprisonment": meta.get("imprisonment", 0),
                    "death_penalty": meta.get("death_penalty", False),
                    "life_imprisonment": meta.get("life_imprisonment", False),
                    "punish_of_money": meta.get("punish_of_money", 0)
                }
                
                cases.append(case_data)
            
            # 获取总数（仅第一批时计算）
            total_count = 150327  # 已知总数，避免每次都查询
            if batch == 0:
                try:
                    total_count = collection.count()
                except:
                    pass
            
            has_more = (offset + len(documents)) < total_count
            
            result = {
                "cases": cases,
                "total": total_count,
                "batch": batch,
                "batch_size": batch_size,
                "loaded": offset + len(cases),
                "has_more": has_more
            }
            
            # 缓存结果（缓存30分钟）
            cache.set(cache_key, result, ttl=1800)
            print(f"[已缓存] 案例批次 {batch} (共 {len(cases)} 条, has_more={has_more})")
            
            return jsonify(result)
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    
    @app.route('/api/cases/<int:case_id>/detail', methods=['GET'])
    def get_case_detail(case_id):
        """
        获取单条案例的完整内容（延迟加载）
        
        参数:
        - case_id: 案例ID
        
        返回:
        {
            "id": 1,
            "fact": "完整案情描述...",
            "accusation": "罪名",
            "imprisonment": 36,
            ...
        }
        """
        try:
            # 尝试从缓存获取
            cache = get_cache()
            cache_key = f"case_detail:{case_id}"
            cached_result = cache.get(cache_key)
            
            if cached_result is not None:
                print(f"[缓存命中] 案例详情: id={case_id}")
                return jsonify(cached_result)
            
            print(f"[缓存未命中] 正在加载案例详情: id={case_id}")
            vs = get_vectorstore("criminal_cases")
            collection = vs._collection
            
            # 获取指定ID的数据
            all_data = collection.get(
                include=["documents", "metadatas"],
                offset=case_id,
                limit=1
            )
            
            if not all_data.get("documents"):
                return jsonify({"error": "未找到该案例"}), 404
            
            doc = all_data["documents"][0]
            meta = all_data["metadatas"][0] if all_data.get("metadatas") else {}
            
            result = {
                "id": case_id,
                "fact": doc,  # 完整案情
                "accusation": meta.get("accusation", ""),
                "imprisonment": meta.get("imprisonment", 0),
                "death_penalty": meta.get("death_penalty", False),
                "life_imprisonment": meta.get("life_imprisonment", False),
                "punish_of_money": meta.get("punish_of_money", 0),
                "criminals": meta.get("criminals", "")
            }
            
            # 缓存结果（缓存1小时）
            cache.set(cache_key, result, ttl=3600)
            
            return jsonify(result)
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/cases/stats', methods=['GET'])
    def get_case_stats():
        """
        获取案例库统计信息（刑期分布等 - 带缓存优化）
        
        返回:
        {
            "total_cases": 10000,
            "imprisonment_ranges": [
                {"range": "0-6个月", "min": 0, "max": 6, "count": 1000},
                ...
            ]
        }
        """
        try:
            # 尝试从缓存获取
            cache = get_cache()
            cache_key = "case_stats"
            cached_result = cache.get(cache_key)
            
            if cached_result is not None:
                print("[缓存命中] 案例统计")
                return jsonify(cached_result)
            
            print("[缓存未命中] 正在加载案例统计...")
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
                
                # 检查是否死刑或无期
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
            
            # 缓存结果（缓存1小时）
            cache.set(cache_key, result, ttl=3600)
            print(f"[已缓存] 案例统计 (共 {total} 个案例)")
            
            return jsonify(result)
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    
    @app.route('/api/cases/search', methods=['POST'])
    def search_cases():
        """
        搜索案例（优化版 - 支持缓存和智能分页）
        
        请求体:
        {
            "query": "搜索关键词（可选）",
            "accusation": "罪名筛选（可选）",
            "imprisonment_min": 0,  // 刑期最小值（月，可选）
            "imprisonment_max": 120,  // 刑期最大值（月，可选）
            "page": 1,
            "page_size": 10
        }
        
        返回:
        {
            "results": [{"fact": "...", "accusation": "...", "imprisonment": 36}],
            "total": 100,
            "page": 1,
            "page_size": 10
        }
        """
        try:
            data = request.get_json()
            query = data.get('query', '')
            accusation = data.get('accusation', '')
            imprisonment_min = data.get('imprisonment_min')
            imprisonment_max = data.get('imprisonment_max')
            page = data.get('page', 1)
            page_size = data.get('page_size', 10)
            
            # 构造缓存键
            cache = get_cache()
            cache_key = f"case_search:{query}:{accusation}:{imprisonment_min}:{imprisonment_max}:{page}:{page_size}"
            
            # 尝试从缓存获取
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                print(f"[缓存命中] 案例搜索: query={query}, accusation={accusation}, page={page}")
                return jsonify(cached_result)
            
            vs = get_vectorstore("criminal_cases")
            
            if query:
                # 语义搜索（限制为合理的范围）
                search_k = min(300, page * page_size + 150)  # 动态调整搜索范围
                search_results = vs.similarity_search(query, k=search_k)
            else:
                # 使用智能批量加载策略，避免一次性加载所有数据
                collection = vs._collection
                
                # 计算需要的数据范围
                buffer_pages = 5  # 缓冲页数
                offset = max(0, (page - buffer_pages) * page_size)
                limit = (buffer_pages * 2 + 1) * page_size
                
                # 使用 offset 和 limit 进行批量查询
                all_data = collection.get(
                    include=["documents", "metadatas"],
                    offset=offset,
                    limit=limit
                )
                
                search_results = [
                    Document(page_content=doc, metadata=meta or {})
                    for doc, meta in zip(
                        all_data.get("documents", []),
                        all_data.get("metadatas", [])
                    )
                ]
            
            # 筛选
            results = []
            for doc in search_results:
                meta = doc.metadata
                
                # 按罪名筛选
                if accusation:
                    doc_acc = meta.get("accusation", "")
                    if accusation not in doc_acc:
                        continue
                
                # 按刑期筛选
                imprisonment = meta.get("imprisonment", 0)
                if imprisonment_min is not None and imprisonment < imprisonment_min:
                    continue
                if imprisonment_max is not None and imprisonment > imprisonment_max:
                    continue
                
                results.append(doc)
            
            # 分页
            total = len(results)
            start = (page - 1) * page_size
            # 如果是批量加载，需要调整 start
            if not query:
                start = start - offset
            
            end = start + page_size
            paged_results = results[start:end] if start >= 0 else results[:page_size]
            
            # 格式化结果
            formatted = []
            for doc in paged_results:
                meta = doc.metadata
                formatted.append({
                    "fact": doc.page_content[:500] + ("..." if len(doc.page_content) > 500 else ""),
                    "full_fact": doc.page_content,
                    "accusation": meta.get("accusation", ""),
                    "imprisonment": meta.get("imprisonment", 0),
                    "death_penalty": meta.get("death_penalty", False),
                    "life_imprisonment": meta.get("life_imprisonment", False),
                    "punish_of_money": meta.get("punish_of_money", 0),
                    "criminals": meta.get("criminals", "")
                })
            
            result = {
                "results": formatted,
                "total": total,
                "page": page,
                "page_size": page_size
            }
            
            # 缓存结果（缓存5分钟）
            cache.set(cache_key, result, ttl=300)
            
            return jsonify(result)
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

