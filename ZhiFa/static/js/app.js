      // ===== 国际化系统 (i18n) =====
      const I18n = {
        // 当前语言
        currentLocale: "zh-CN",

        // 翻译资源缓存
        locales: {},

        // 支持的语言列表
        supportedLocales: ["zh-CN", "en-US", "ja-JP", "zh-TW"],

        // 语言显示名称
        localeNames: {
          "zh-CN": "简体中文",
          "en-US": "English",
          "ja-JP": "日本語",
          "zh-TW": "繁體中文",
        },

        // 初始化
        async init() {
          // 从 localStorage 读取用户语言偏好
          const savedLocale = localStorage.getItem("locale");
          if (savedLocale && this.supportedLocales.includes(savedLocale)) {
            this.currentLocale = savedLocale;
          }

          // 预加载所有语言资源（提高切换速度）
          await this.preloadAllLocales();

          // 应用翻译
          this.updateDOM();

          // 更新语言选择器
          const langSelect = document.getElementById("language-select");
          if (langSelect) {
            langSelect.value = this.currentLocale;
          }

          // 更新 HTML lang 属性
          document.documentElement.lang = this.currentLocale;

          console.log(`[i18n] 初始化完成，当前语言: ${this.currentLocale}`);
        },

        // 预加载所有语言资源
        async preloadAllLocales() {
          const promises = this.supportedLocales.map((locale) =>
            this.loadLocale(locale)
          );
          await Promise.all(promises);
        },

        // 加载语言资源文件
        async loadLocale(locale) {
          if (this.locales[locale]) {
            return this.locales[locale]; // 已缓存
          }

          try {
            const response = await fetch(`/static/locales/${locale}.json`);
            if (!response.ok) throw new Error(`Failed to load ${locale}`);

            this.locales[locale] = await response.json();
            console.log(`[i18n] 加载语言资源: ${locale}`);
            return this.locales[locale];
          } catch (error) {
            console.error(`[i18n] 加载语言失败: ${locale}`, error);
            // 回退到中文
            if (locale !== "zh-CN") {
              return this.loadLocale("zh-CN");
            }
            return {};
          }
        },

        // 切换语言
        async setLocale(locale) {
          if (!this.supportedLocales.includes(locale)) {
            console.warn(`[i18n] 不支持的语言: ${locale}`);
            return;
          }

          if (locale === this.currentLocale) return;

          // 加载新语言（如果尚未加载）
          await this.loadLocale(locale);

          // 更新当前语言
          this.currentLocale = locale;
          localStorage.setItem("locale", locale);

          // 更新 HTML lang 属性
          document.documentElement.lang = locale;

          // 使用 requestAnimationFrame 进行批量 DOM 更新，避免卡顿
          requestAnimationFrame(() => {
            this.updateDOM();
            // 更新页面标题
            document.title = this.t("app.title");
          });

          console.log(`[i18n] 语言已切换: ${locale}`);
        },

        // 获取翻译文本
        t(key, params = {}) {
          const keys = key.split(".");
          let value = this.locales[this.currentLocale];

          for (const k of keys) {
            if (value && typeof value === "object") {
              value = value[k];
            } else {
              value = undefined;
              break;
            }
          }

          // 如果找不到，回退到中文
          if (value === undefined && this.currentLocale !== "zh-CN") {
            value = this.locales["zh-CN"];
            for (const k of keys) {
              if (value && typeof value === "object") {
                value = value[k];
              } else {
                value = key; // 最终返回 key 本身
                break;
              }
            }
          }

          // 如果还是没有，返回 key
          if (value === undefined) {
            return key;
          }

          // 替换参数 {%raw%}{{paramName}}{%endraw%}
          if (typeof value === "string" && Object.keys(params).length > 0) {
            return value.replace(/\{\{(\w+)\}\}/g, (_, paramName) => {
              return params[paramName] !== undefined
                ? params[paramName]
                : "{{" + paramName + "}}";
            });
          }

          return value;
        },

        // 更新所有带 data-i18n 属性的 DOM 元素
        updateDOM() {
          // 更新文本内容
          document.querySelectorAll("[data-i18n]").forEach((el) => {
            const key = el.getAttribute("data-i18n");
            const text = this.t(key);
            if (text !== key) {
              el.textContent = text;
            }
          });

          // 更新 placeholder
          document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
            const key = el.getAttribute("data-i18n-placeholder");
            const text = this.t(key);
            if (text !== key) {
              el.placeholder = text;
            }
          });

          // 更新 title 属性（tooltip）
          document.querySelectorAll("[data-i18n-title]").forEach((el) => {
            const key = el.getAttribute("data-i18n-title");
            const text = this.t(key);
            if (text !== key) {
              el.title = text;
            }
          });

          // 更新 aria-label
          document.querySelectorAll("[data-i18n-aria]").forEach((el) => {
            const key = el.getAttribute("data-i18n-aria");
            const text = this.t(key);
            if (text !== key) {
              el.setAttribute("aria-label", text);
            }
          });

          // 更新 Logo 文本（特殊处理）
          const logoText = document.querySelector(".logo-icon");
          if (logoText) {
            logoText.textContent = this.t("app.logoText");
          }
        },
      };

      // 页面加载时初始化 i18n
      document.addEventListener("DOMContentLoaded", () => {
        I18n.init();
      });

      // ===== 详情模态框功能 =====

      // 全局存储当前显示的数据
      let currentDetailData = null;

      // 打开法律法规详情 - 延迟加载完整内容
      async function openLawDetail(itemId, previewItem = null) {
        const titleEl = document.getElementById("detail-modal-title");
        const bodyEl = document.getElementById("detail-modal-body");

        // 先显示预览信息和加载状态
        if (previewItem) {
          titleEl.innerHTML = `
                <span>${escapeHtmlGlobal(
                  previewItem.law_name || "未知法律"
                )}</span>
                <span class="badge">${escapeHtmlGlobal(
                  previewItem.category || "法律法规"
                )}</span>
            `;
        } else {
          titleEl.innerHTML = `<span>${I18n.t("common.loading")}</span>`;
        }

        bodyEl.innerHTML = `
            <div class="detail-loading">
                <div class="detail-loading-spinner"></div>
                <div class="detail-loading-text">${I18n.t(
                  "common.loading"
                )}</div>
            </div>
        `;

        showDetailModal();

        try {
          // 从API获取完整内容
          const response = await fetch(`/api/laws/${itemId}/detail`);
          if (!response.ok) {
            throw new Error("加载失败");
          }

          const item = await response.json();
          currentDetailData = { type: "law", data: item };

          // 更新标题
          titleEl.innerHTML = `
                <span>${escapeHtmlGlobal(item.law_name || "未知法律")}</span>
                <span class="badge">${escapeHtmlGlobal(
                  item.category || "法律法规"
                )}</span>
            `;

          // 渲染完整内容
          bodyEl.innerHTML = `
                <div class="detail-meta">
                    <div class="detail-meta-item">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                            <polyline points="14 2 14 8 20 8"></polyline>
                        </svg>
                        <span>${escapeHtmlGlobal(
                          item.law_name || "未知法律"
                        )}</span>
                    </div>
                    <div class="detail-meta-item">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                            <line x1="16" y1="2" x2="16" y2="6"></line>
                            <line x1="8" y1="2" x2="8" y2="6"></line>
                            <line x1="3" y1="10" x2="21" y2="10"></line>
                        </svg>
                        <span>${escapeHtmlGlobal(
                          item.category || "其他"
                        )}</span>
                    </div>
                </div>
                <div class="detail-section">
                    <div class="detail-section-title">${I18n.t(
                      "laws.pageTitle"
                    )}</div>
                    <div class="detail-content">${escapeHtmlGlobal(
                      item.content || I18n.t("common.noData")
                    )}</div>
                </div>
            `;
        } catch (error) {
          console.error("加载法律详情失败:", error);
          bodyEl.innerHTML = `
                <div class="detail-error">
                    <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="8" x2="12" y2="12"></line>
                        <line x1="12" y1="16" x2="12.01" y2="16"></line>
                    </svg>
                    <div>${I18n.t("notifications.loadingFailed")}</div>
                </div>
            `;
        }
      }

      // 打开案例详情 - 延迟加载完整内容
      async function openCaseDetail(itemId, previewItem = null) {
        const titleEl = document.getElementById("detail-modal-title");
        const bodyEl = document.getElementById("detail-modal-body");

        // 先显示预览信息和加载状态
        if (previewItem) {
          titleEl.innerHTML = `
                <span>${I18n.t("cases.pageTitle")}</span>
                <span class="badge">${escapeHtmlGlobal(
                  previewItem.accusation || ""
                )}</span>
            `;
        } else {
          titleEl.innerHTML = `<span>${I18n.t("common.loading")}</span>`;
        }

        bodyEl.innerHTML = `
            <div class="detail-loading">
                <div class="detail-loading-spinner"></div>
                <div class="detail-loading-text">${I18n.t(
                  "common.loading"
                )}</div>
            </div>
        `;

        showDetailModal();

        try {
          // 从API获取完整内容
          const response = await fetch(`/api/cases/${itemId}/detail`);
          if (!response.ok) {
            throw new Error("加载失败");
          }

          const item = await response.json();
          currentDetailData = { type: "case", data: item };

          // 获取刑罚文本
          let punishment = "";
          if (item.death_penalty) {
            punishment = "死刑";
          } else if (item.life_imprisonment) {
            punishment = "无期徒刑";
          } else {
            const months = item.imprisonment || 0;
            if (months >= 12) {
              const years = Math.floor(months / 12);
              const remainMonths = months % 12;
              punishment =
                remainMonths > 0
                  ? `${years}年${remainMonths}个月`
                  : `${years}年`;
            } else {
              punishment = months + "个月";
            }
          }

          // 更新标题
          titleEl.innerHTML = `
                <span>${I18n.t("cases.pageTitle")}</span>
                <span class="badge">${escapeHtmlGlobal(
                  item.accusation || ""
                )}</span>
            `;

          let metaHtml = `
                <div class="detail-meta-item highlight">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polyline points="12 6 12 12 16 14"></polyline>
                    </svg>
                    <span>刑期：${escapeHtmlGlobal(punishment)}</span>
                </div>
            `;

          if (item.punish_of_money > 0) {
            metaHtml += `
                    <div class="detail-meta-item">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="12" y1="1" x2="12" y2="23"></line>
                            <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
                        </svg>
                        <span>罚金：${item.punish_of_money.toLocaleString()} 元</span>
                    </div>
                `;
          }

          // 渲染完整内容
          bodyEl.innerHTML = `
                <div class="detail-meta">
                    ${metaHtml}
                </div>
                <div class="detail-section">
                    <div class="detail-section-title">${I18n.t(
                      "case.inputTitle"
                    )}</div>
                    <div class="detail-content">${escapeHtmlGlobal(
                      item.fact || I18n.t("common.noData")
                    )}</div>
                </div>
            `;
        } catch (error) {
          console.error("加载案例详情失败:", error);
          bodyEl.innerHTML = `
                <div class="detail-error">
                    <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="8" x2="12" y2="12"></line>
                        <line x1="12" y1="16" x2="12.01" y2="16"></line>
                    </svg>
                    <div>${I18n.t("notifications.loadingFailed")}</div>
                </div>
            `;
        }
      }

      // 显示模态框
      function showDetailModal() {
        const overlay = document.getElementById("detail-modal-overlay");
        overlay.classList.add("active");
        document.body.style.overflow = "hidden";
      }

      // 关闭模态框
      function closeDetailModal() {
        const overlay = document.getElementById("detail-modal-overlay");
        overlay.classList.remove("active");
        document.body.style.overflow = "";
        currentDetailData = null;
      }

      // 全局HTML转义函数
      function escapeHtmlGlobal(str) {
        return String(str || "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#39;");
      }

      // ESC键关闭模态框
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
          closeDetailModal();
        }
      });

      // ===== 搜索优化工具 =====

      // 1. 防抖函数 - 避免频繁的API请求
      function debounce(func, wait, immediate = false) {
        let timeout;
        return function executedFunction(...args) {
          const later = () => {
            timeout = null;
            if (!immediate) func.apply(this, args);
          };
          const callNow = immediate && !timeout;
          clearTimeout(timeout);
          timeout = setTimeout(later, wait);
          if (callNow) func.apply(this, args);
        };
      }

      // 2. LRU缓存类 - 前端搜索结果缓存
      class LRUCache {
        constructor(maxSize = 50) {
          this.maxSize = maxSize;
          this.cache = new Map();
        }

        get(key) {
          if (!this.cache.has(key)) return null;
          const value = this.cache.get(key);
          // 移到最前面（最近使用）
          this.cache.delete(key);
          this.cache.set(key, value);
          return value;
        }

        set(key, value) {
          if (this.cache.has(key)) {
            this.cache.delete(key);
          } else if (this.cache.size >= this.maxSize) {
            // 删除最早添加的项
            const firstKey = this.cache.keys().next().value;
            this.cache.delete(firstKey);
          }
          this.cache.set(key, value);
        }

        clear() {
          this.cache.clear();
        }
      }

      // 创建搜索缓存实例
      const lawSearchCache = new LRUCache(30);
      const caseSearchCache = new LRUCache(30);

      // 3. AbortController管理器 - 取消未完成的请求
      class RequestManager {
        constructor() {
          this.controllers = new Map();
        }

        getController(key) {
          // 取消之前的请求
          if (this.controllers.has(key)) {
            this.controllers.get(key).abort();
          }
          // 创建新的控制器
          const controller = new AbortController();
          this.controllers.set(key, controller);
          return controller;
        }

        clear(key) {
          if (this.controllers.has(key)) {
            this.controllers.delete(key);
          }
        }
      }

      const requestManager = new RequestManager();

      // 4. 搜索历史管理
      class SearchHistory {
        constructor(key, maxItems = 10) {
          this.storageKey = key;
          this.maxItems = maxItems;
        }

        getHistory() {
          try {
            return JSON.parse(localStorage.getItem(this.storageKey) || "[]");
          } catch {
            return [];
          }
        }

        addItem(query) {
          if (!query.trim()) return;
          let history = this.getHistory();
          // 移除重复项
          history = history.filter((item) => item !== query);
          // 添加到开头
          history.unshift(query);
          // 限制数量
          if (history.length > this.maxItems) {
            history = history.slice(0, this.maxItems);
          }
          localStorage.setItem(this.storageKey, JSON.stringify(history));
        }

        clearHistory() {
          localStorage.removeItem(this.storageKey);
        }
      }

      const lawSearchHistory = new SearchHistory("law_search_history");
      const caseSearchHistory = new SearchHistory("case_search_history");

      // 5. 关键词高亮函数
      function highlightKeywords(text, keywords) {
        if (!keywords || !keywords.trim()) return escapeHtml(text);
        const escaped = escapeHtml(text);
        const words = keywords.trim().split(/\s+/);
        let result = escaped;
        for (const word of words) {
          if (word.length > 0) {
            const regex = new RegExp(
              `(${word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`,
              "gi"
            );
            result = result.replace(
              regex,
              '<mark class="search-highlight">$1</mark>'
            );
          }
        }
        return result;
      }

      // 6. 骨架屏生成器
      function generateSkeleton(type, count = 5) {
        let html = "";
        if (type === "law") {
          for (let i = 0; i < count; i++) {
            html += `<div class="result-card skeleton-card">
                    <div class="result-header">
                        <div class="skeleton-line skeleton-title"></div>
                        <div class="skeleton-line skeleton-badge"></div>
                    </div>
                    <div class="result-content">
                        <div class="skeleton-line skeleton-text"></div>
                        <div class="skeleton-line skeleton-text short"></div>
                        <div class="skeleton-line skeleton-text medium"></div>
                    </div>
                </div>`;
          }
        } else if (type === "case") {
          for (let i = 0; i < count; i++) {
            html += `<div class="case-card skeleton-card">
                    <div class="case-header">
                        <div class="skeleton-line skeleton-badge"></div>
                        <div class="skeleton-line skeleton-badge"></div>
                    </div>
                    <div class="case-body">
                        <div class="skeleton-line skeleton-text"></div>
                        <div class="skeleton-line skeleton-text short"></div>
                        <div class="skeleton-line skeleton-text medium"></div>
                        <div class="skeleton-line skeleton-text"></div>
                    </div>
                </div>`;
          }
        }
        return html;
      }

      // 7. 格式化搜索时间
      function formatSearchTime(ms) {
        if (ms < 1000) return `${ms}ms`;
        return `${(ms / 1000).toFixed(2)}s`;
      }

      // ===== 虚拟滚动类 =====
      class VirtualScroll {
        constructor(options) {
          this.container = options.container;
          this.viewport = options.viewport;
          this.content = options.content;
          this.spacer = options.spacer;
          this.itemHeight = options.itemHeight || 120;
          this.bufferSize = options.bufferSize || 5;
          this.columns = options.columns || 1;
          this.renderItem = options.renderItem;
          this.onScroll = options.onScroll;

          this.items = [];
          this.filteredItems = [];
          this.scrollTop = 0;
          this.viewportHeight = 0;
          this.isScrolling = false;
          this.scrollTimeout = null;

          this.init();
        }

        init() {
          this.viewport.addEventListener(
            "scroll",
            this.handleScroll.bind(this),
            { passive: true }
          );

          // 监听窗口大小变化
          const resizeObserver = new ResizeObserver(() => {
            this.updateViewportHeight();
            this.render();
          });
          resizeObserver.observe(this.viewport);
        }

        updateViewportHeight() {
          this.viewportHeight =
            this.viewport.clientHeight || this.viewport.offsetHeight || 600;
          // 确保有最小高度
          if (this.viewportHeight < 100) {
            this.viewportHeight = 600;
          }
        }

        setItems(items) {
          this.items = items;
          this.filteredItems = items;
          // 延迟一帧确保DOM已渲染
          requestAnimationFrame(() => {
            this.updateViewportHeight();
            this.updateSpacerHeight();
            this.render();
          });
        }

        filterItems(filterFn) {
          if (typeof filterFn === "function") {
            this.filteredItems = this.items.filter(filterFn);
          } else {
            this.filteredItems = this.items;
          }
          this.viewport.scrollTop = 0;
          this.scrollTop = 0;
          this.updateSpacerHeight();
          this.render();
          return this.filteredItems.length;
        }

        searchItems(query, fields = ["content", "law_name"]) {
          if (!query || query.trim() === "") {
            this.filteredItems = this.items;
          } else {
            const searchTerms = query
              .toLowerCase()
              .split(/\s+/)
              .filter((t) => t);
            this.filteredItems = this.items.filter((item) => {
              const searchText = fields
                .map((f) => (item[f] || "").toLowerCase())
                .join(" ");
              return searchTerms.every((term) => searchText.includes(term));
            });
          }
          this.viewport.scrollTop = 0;
          this.scrollTop = 0;
          this.updateSpacerHeight();
          this.render();
          return this.filteredItems.length;
        }

        updateSpacerHeight() {
          const rowCount = Math.ceil(this.filteredItems.length / this.columns);
          const totalHeight = rowCount * this.itemHeight;
          this.spacer.style.height = `${totalHeight}px`;
        }

        handleScroll() {
          this.scrollTop = this.viewport.scrollTop;

          // 使用requestAnimationFrame优化渲染
          if (!this.isScrolling) {
            this.isScrolling = true;
            requestAnimationFrame(() => {
              this.render();
              this.isScrolling = false;
            });
          }

          // 触发滚动回调
          if (this.onScroll) {
            clearTimeout(this.scrollTimeout);
            this.scrollTimeout = setTimeout(() => {
              const { startIndex, endIndex } = this.getVisibleRange();
              this.onScroll({
                scrollTop: this.scrollTop,
                startIndex,
                endIndex,
                total: this.filteredItems.length,
              });
            }, 50);
          }
        }

        getVisibleRange() {
          // 确保viewportHeight有效
          if (!this.viewportHeight || this.viewportHeight < 100) {
            this.updateViewportHeight();
          }

          const startRow = Math.max(
            0,
            Math.floor(this.scrollTop / this.itemHeight) - this.bufferSize
          );
          const visibleRows =
            Math.ceil(this.viewportHeight / this.itemHeight) || 10;
          const endRow = Math.min(
            Math.ceil(this.filteredItems.length / this.columns),
            startRow + visibleRows + this.bufferSize * 2
          );
          const startIndex = startRow * this.columns;
          const endIndex = Math.min(this.filteredItems.length, endRow * this.columns);
          return { startIndex, endIndex };
        }

        render() {
          if (this.filteredItems.length === 0) {
            this.content.innerHTML = '<div class="empty-hint">暂无数据</div>';
            return;
          }

          const { startIndex, endIndex } = this.getVisibleRange();
          const visibleItems = this.filteredItems.slice(startIndex, endIndex);

          // 设置内容区域的偏移
          const startRow = Math.floor(startIndex / this.columns);
          const offsetY = startRow * this.itemHeight;
          this.content.style.transform = `translateY(${offsetY}px)`;

          // 渲染可见项
          let html = "";
          visibleItems.forEach((item, index) => {
            html += this.renderItem(item, startIndex + index);
          });

          this.content.innerHTML =
            html || '<div class="empty-hint">暂无数据</div>';

          console.log(
            `[虚拟滚动] 渲染 ${visibleItems.length} 项 (${startIndex}-${endIndex}/${this.filteredItems.length}), viewport=${this.viewportHeight}px`
          );
        }

        scrollToTop() {
          this.viewport.scrollTo({ top: 0, behavior: "smooth" });
        }

        scrollToIndex(index) {
          const scrollTop = index * this.itemHeight;
          this.viewport.scrollTo({ top: scrollTop, behavior: "smooth" });
        }

        getStats() {
          return {
            total: this.items.length,
            filtered: this.filteredItems.length,
            itemHeight: this.itemHeight,
          };
        }
      }

      // ===== 法律法规数据管理器 =====
      class LawDataManager {
        constructor() {
          this.allLaws = [];
          this.isLoaded = false;
          this.isLoading = false;
          this.loadPromise = null;
          this.virtualScroll = null;
          this.currentCategory = "";
          this.currentQuery = "";
        }

        async loadAllLaws(forceRefresh = false) {
          // 如果已加载且不是强制刷新，直接返回
          if (this.isLoaded && !forceRefresh) {
            return this.allLaws;
          }

          // 如果正在加载，返回现有promise
          if (this.isLoading && this.loadPromise) {
            return this.loadPromise;
          }

          this.isLoading = true;
          // 注意：不再在这里设置 this.currentCategory，保留筛选用的分类值

          this.loadPromise = new Promise(async (resolve, reject) => {
            try {
              const startTime = performance.now();

              // 显示加载状态
              this.showLoadingState();

              // 始终加载全部数据，筛选在前端进行
              const url = "/api/laws/all?lite=true";

              const response = await fetch(url);
              const data = await response.json();

              if (data.error) {
                throw new Error(data.error);
              }

              this.allLaws = data.laws || [];
              this.isLoaded = true;

              const loadTime = performance.now() - startTime;
              console.log(
                `[性能] 加载 ${
                  this.allLaws.length
                } 条法律数据，耗时 ${loadTime.toFixed(0)}ms`
              );

              // 隐藏加载状态
              this.hideLoadingState();

              // 初始化虚拟滚动
              this.initVirtualScroll();

              // 更新统计信息
              this.updateStats(loadTime);

              resolve(this.allLaws);
            } catch (error) {
              console.error("加载法律数据失败:", error);
              this.hideLoadingState();
              reject(error);
            } finally {
              this.isLoading = false;
            }
          });

          return this.loadPromise;
        }

        showLoadingState() {
          const container = document.getElementById("law-virtual-container");
          if (!container) return;

          // 添加加载覆盖层
          const overlay = document.createElement("div");
          overlay.className = "data-loading-overlay";
          overlay.id = "law-loading-overlay";
          overlay.innerHTML = `
                <div class="data-loading-spinner"></div>
                <div class="data-loading-text">正在加载法律法规数据库...</div>
                <div class="data-loading-progress" id="law-loading-progress">准备中...</div>
            `;
          container.appendChild(overlay);
        }

        hideLoadingState() {
          const overlay = document.getElementById("law-loading-overlay");
          if (overlay) {
            overlay.style.opacity = "0";
            setTimeout(() => overlay.remove(), 300);
          }
        }

        initVirtualScroll() {
          const viewport = document.getElementById("law-results");
          const content = document.getElementById("law-content");
          const spacer = document.getElementById("law-spacer");
          const container = document.getElementById("law-virtual-container");
          const scrollInfo = document.getElementById("law-scroll-info");

          if (!viewport || !content || !spacer) {
            console.error("虚拟滚动容器未找到");
            return;
          }

          // 创建虚拟滚动实例
          this.virtualScroll = new VirtualScroll({
            container,
            viewport,
            content,
            spacer,
            itemHeight: 250, // 与案例库一致
            bufferSize: 10,
            renderItem: this.renderLawItem.bind(this),
            onScroll: (info) => {
              // 更新滚动位置信息
              const posEl = scrollInfo.querySelector(".scroll-position");
              if (posEl && info.total > 0) {
                posEl.textContent = `显示 ${info.startIndex + 1} - ${Math.min(
                  info.endIndex,
                  info.total
                )} / ${info.total} 条`;
              }
            },
          });

          // 设置数据
          this.virtualScroll.setItems(this.allLaws);

          // 绑定回到顶部按钮
          const scrollToTopBtn = scrollInfo.querySelector(".scroll-to-top");
          if (scrollToTopBtn) {
            scrollToTopBtn.onclick = () => this.virtualScroll.scrollToTop();
          }
        }

        renderLawItem(item, index) {
          const query = this.currentQuery;

          // 先转义HTML特殊字符
          const escapeHtml = (str) => {
            return String(str || "")
              .replace(/&/g, "&amp;")
              .replace(/</g, "&lt;")
              .replace(/>/g, "&gt;")
              .replace(/"/g, "&quot;")
              .replace(/'/g, "&#39;");
          };

          let content = escapeHtml(item.content || "");
          let lawName = escapeHtml(item.law_name || "未知法律");
          let category = escapeHtml(item.category || "");

          // 高亮搜索关键词（在转义后进行）
          if (query) {
            const terms = query.split(/\s+/).filter((t) => t);
            terms.forEach((term) => {
              const escapedTerm = escapeHtml(term);
              const regex = new RegExp(
                `(${escapedTerm.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`,
                "gi"
              );
              content = content.replace(regex, "<mark>$1</mark>");
              lawName = lawName.replace(regex, "<mark>$1</mark>");
            });
          }

          // 使用item.id作为真实ID，确保API调用正确
          const itemId = item.id !== undefined ? item.id : index;

          return `<div class="result-card clickable" data-id="${itemId}" onclick="openLawDetail(${itemId})">
                <div class="result-body">
                    <div class="result-content">${content}</div>
                </div>
                <div class="result-meta">
                    <div class="result-meta-right">
                        <div class="result-meta-tags">
                            <span class="result-meta-chip accent">${category}</span>
                        </div>
                        <span class="click-hint">
                            详情
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M5 12h14"></path>
                                <path d="M12 5l7 7-7 7"></path>
                            </svg>
                        </span>
                    </div>
                </div>
            </div>`;
        }

        search(query) {
          this.currentQuery = query;

          if (!this.virtualScroll) {
            console.warn("虚拟滚动未初始化");
            return 0;
          }

          const startTime = performance.now();

          // 同时考虑分类和搜索条件
          const category = this.currentCategory;

          const filterFn = (item) => {
            // 先检查分类
            if (category) {
              const itemCategory = (item.category || "").trim();
              const targetCategory = category.trim();

              // 如果条目没有分类信息，则不匹配
              if (!itemCategory) return false;

              // 精确匹配或包含匹配
              const categoryMatch =
                itemCategory === targetCategory ||
                itemCategory.includes(targetCategory) ||
                targetCategory.includes(itemCategory);
              if (!categoryMatch) return false;
            }

            // 再检查关键词
            if (query && query.trim()) {
              const searchTerms = query
                .toLowerCase()
                .split(/\s+/)
                .filter((t) => t);
              const searchText = `${item.content || ""} ${
                item.law_name || ""
              } ${item.category || ""}`.toLowerCase();
              if (!searchTerms.every((term) => searchText.includes(term))) {
                return false;
              }
            }

            return true;
          };

          const count = this.virtualScroll.filterItems(filterFn);
          const searchTime = performance.now() - startTime;

          console.log(
            `[性能] 前端搜索完成: 分类="${category}", 关键词="${query}", ${count} 条结果，耗时 ${searchTime.toFixed(
              0
            )}ms`
          );

          this.updateStats(searchTime, count, true);
          return count;
        }

        filterByCategory(category) {
          console.log("[分类筛选] 设置分类:", category);
          this.currentCategory = category;

          if (!this.virtualScroll) {
            console.warn("[分类筛选] 虚拟滚动未初始化");
            return 0;
          }

          // 打印前3条数据的分类信息，用于调试
          if (this.allLaws.length > 0) {
            console.log("[分类筛选] 数据示例 - 前3条数据的分类:");
            this.allLaws.slice(0, 3).forEach((item, i) => {
              console.log(
                `  ${i + 1}. category="${item.category}", law_name="${
                  item.law_name
                }"`
              );
            });
          }

          // 使用search方法同时处理分类和关键词
          return this.search(this.currentQuery);
        }

        updateStats(time, count = null, isInstant = false) {
          const resultCountEl = document.getElementById("law-result-count");
          if (!resultCountEl) return;

          const total = count !== null ? count : this.allLaws.length;

          // 简洁的徽章样式
          resultCountEl.textContent = total.toLocaleString("zh-CN") + " 条";
        }
      }

      // 创建法律数据管理器实例
      const lawDataManager = new LawDataManager();
      window.lawDataManager = lawDataManager;

      // ===== 主题切换 =====
      function setTheme(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        localStorage.setItem("theme", theme);

        document.querySelectorAll(".theme-btn").forEach((btn) => {
          btn.classList.remove("active");
          if (btn.dataset.theme === theme) {
            btn.classList.add("active");
          }
        });
      }

      // 初始化主题
      const savedTheme = localStorage.getItem("theme") || "dark";
      setTheme(savedTheme);

      // ===== 系统设置功能 =====

      // 切换API密钥可见性
      function toggleApiKeyVisibility() {
        const input = document.getElementById("api-key-input");
        const icon = document.getElementById("eye-icon");
        if (input.type === "password") {
          input.type = "text";
          icon.innerHTML =
            '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>';
        } else {
          input.type = "password";
          icon.innerHTML =
            '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
        }
      }

      // 测试API连接（进行真实的API调用测试）
      async function testApiConnection() {
        const statusEl = document.getElementById("api-status");
        const apiKey = document.getElementById("api-key-input").value;
        const model = document.getElementById("llm-model-select").value;

        if (!apiKey) {
          statusEl.textContent = I18n.t("errors.apiKeyRequired");
          statusEl.className = "connection-status error";
          return;
        }

        statusEl.textContent = I18n.t("settings.checking");
        statusEl.className = "connection-status";

        try {
          const response = await fetch("/api/settings/test-connection", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              api_key: apiKey,
              model: model, // 发送选择的模型进行测试
            }),
          });
          const data = await response.json();

          if (data.success) {
            statusEl.textContent =
              data.message || I18n.t("notifications.connectionSuccess");
            statusEl.className = "connection-status success";
            showNotification(
              I18n.t("notifications.connectionSuccess"),
              "success"
            );
          } else {
            statusEl.textContent =
              data.message || I18n.t("notifications.connectionFailed");
            statusEl.className = "connection-status error";
            showNotification(
              data.message || I18n.t("notifications.connectionFailed"),
              "error"
            );
          }
        } catch (error) {
          statusEl.textContent = I18n.t("notifications.connectionFailed");
          statusEl.className = "connection-status error";
        }
      }

      // 从设置页面设置主题
      function setThemeFromSettings(theme) {
        setTheme(theme);
        document.querySelectorAll(".theme-option").forEach((btn) => {
          btn.classList.remove("active");
          if (btn.dataset.theme === theme) {
            btn.classList.add("active");
          }
        });
      }

      // 设置字体大小（只缩放主内容区域，侧边栏保持不变）
      function setFontSize(size) {
        document.documentElement.setAttribute("data-font-size", size);
        localStorage.setItem("fontSize", size);

        // 更新按钮状态
        document.querySelectorAll(".font-size-option").forEach((btn) => {
          btn.classList.remove("active");
          if (btn.dataset.size === size) {
            btn.classList.add("active");
          }
        });

        // 使用zoom属性实现界面缩放
        const zoomMap = {
          small: "0.9", // 90%
          medium: "1", // 100%
          large: "1.1", // 110%
        };

        const zoomLevel = zoomMap[size] || "1";

        // 只对主内容区域应用缩放（侧边栏保持原大小）
        const mainContent = document.querySelector(".main-content");
        if (mainContent) {
          mainContent.style.zoom = zoomLevel;
        }

        // 同时更新CSS变量
        document.documentElement.style.setProperty("--ui-zoom", zoomLevel);

        console.log(
          `[界面设置] 字体大小已设置为: ${size} (缩放比例: ${zoomLevel})`
        );
        showNotification(
          `${I18n.t("settings.fontSize")}: ${
            size === "small"
              ? I18n.t("settings.fontSmall")
              : size === "medium"
              ? I18n.t("settings.fontMedium")
              : I18n.t("settings.fontLarge")
          }`,
          "success"
        );
      }

      // 页面加载时立即应用保存的字体大小
      (function initFontSize() {
        const savedFontSize = localStorage.getItem("fontSize") || "medium";
        document.documentElement.setAttribute("data-font-size", savedFontSize);

        const zoomMap = {
          small: "0.9",
          medium: "1",
          large: "1.1",
        };

        const zoomLevel = zoomMap[savedFontSize] || "1";
        document.documentElement.style.setProperty("--ui-zoom", zoomLevel);

        // 页面加载后应用缩放
        window.addEventListener("DOMContentLoaded", () => {
          const mainContent = document.querySelector(".main-content");
          if (mainContent) {
            mainContent.style.zoom = zoomLevel;
          }

          // 首页统计数字动画
          animateHomeStats();
        });

        // 首页统计数字递增动画
        function animateHomeStats() {
          const statValues = document.querySelectorAll(
            ".stats-row .stat-value[data-target]"
          );

          statValues.forEach((element, index) => {
            const target = parseFloat(element.getAttribute("data-target"));
            const duration = 1200; // 1.2秒动画，更快更实用
            const startDelay = index * 150; // 每个数字延迟150ms

            setTimeout(() => {
              let current = 0;
              const increment = target / (duration / 16); // 60fps
              const isPercentage = target < 100 && target > 10;

              const timer = setInterval(() => {
                current += increment;
                if (current >= target) {
                  // 格式化最终数字
                  if (isPercentage) {
                    element.textContent = target + "%";
                  } else if (target >= 10000) {
                    element.textContent = (target / 10000).toFixed(1) + "万+";
                  } else {
                    element.textContent = Math.floor(target) + "+";
                  }
                  clearInterval(timer);
                } else {
                  // 动画过程中的数字显示
                  if (isPercentage) {
                    element.textContent = current.toFixed(1) + "%";
                  } else if (target >= 10000) {
                    element.textContent = (current / 10000).toFixed(1) + "万";
                  } else {
                    element.textContent = Math.floor(current);
                  }
                }
              }, 16);
            }, startDelay);
          });
        }
      })();

      // 语言切换处理
      // 语言切换处理
      async function onLanguageChange(lang) {
        await I18n.setLocale(lang);
        showNotification(I18n.t("notifications.languageChanged"), "success");
      }

      // 温度滑块变化
      document
        .getElementById("temperature-slider")
        ?.addEventListener("input", function () {
          document.getElementById("temperature-value").textContent = this.value;
        });

      // 刷新服务状态
      async function refreshServiceStatus() {
        const btn = document.querySelector(".btn-refresh");
        btn?.classList.add("spinning");

        try {
          const response = await fetch("/api/settings/status");
          const data = await response.json();

          // 更新API连接状态
          updateStatusIndicator("api-connection-status", data.api_connected);
          // 更新LLM状态
          updateStatusIndicator("llm-status", data.llm_loaded);
          // 更新向量库状态
          updateStatusIndicator("vectordb-status", data.vectordb_connected);

          // 更新使用统计
          if (data.stats) {
            document.getElementById("stat-qa-count").textContent =
              data.stats.qa_count || 0;
            document.getElementById("stat-contract-count").textContent =
              data.stats.contract_count || 0;
            document.getElementById("stat-case-count").textContent =
              data.stats.case_count || 0;
          }
        } catch (error) {
          console.error("获取服务状态失败:", error);
          updateStatusIndicator("api-connection-status", false);
          updateStatusIndicator("llm-status", false);
          updateStatusIndicator("vectordb-status", false);
        }

        setTimeout(() => btn?.classList.remove("spinning"), 500);
      }

      // 刷新当前生效的配置
      async function refreshCurrentConfig() {
        try {
          const response = await fetch("/api/settings/current");
          const data = await response.json();

          if (data.success && data.current) {
            const config = data.current;

            // 更新当前配置显示（三个配置项）
            document.getElementById("current-llm-model").textContent =
              config.llm_model || "未配置";
            document.getElementById("current-embedding-model").textContent =
              config.embedding_model || "未配置";
            document.getElementById("current-temperature").textContent =
              config.temperature || "0.7";
            document.getElementById("current-api-status").textContent =
              config.api_key_configured
                ? I18n.t("settings.configured")
                : I18n.t("settings.notConfigured");
            document.getElementById("current-api-status").style.color =
              config.api_key_configured ? "#22c55e" : "#ef4444";
          }
        } catch (error) {
          console.error("获取当前配置失败:", error);
          document.getElementById("current-llm-model").textContent = I18n.t(
            "notifications.loadingFailed"
          );
          document.getElementById("current-embedding-model").textContent =
            I18n.t("notifications.loadingFailed");
          document.getElementById("current-temperature").textContent = I18n.t(
            "notifications.loadingFailed"
          );
          document.getElementById("current-api-status").textContent = I18n.t(
            "notifications.loadingFailed"
          );
        }
      }

      // 更新状态指示器
      function updateStatusIndicator(elementId, isSuccess) {
        const indicator = document.getElementById(elementId);
        if (!indicator) return;

        const dot = indicator.querySelector(".status-dot");
        const text = indicator.querySelector(".status-text");

        dot.classList.remove("pending", "success", "error");
        dot.classList.add(isSuccess ? "success" : "error");
        text.textContent = isSuccess
          ? I18n.t("settings.connected")
          : I18n.t("settings.disconnected");
      }

      // 保存设置
      async function saveSettings() {
        const settings = {
          api_key: document.getElementById("api-key-input").value,
          llm_model: document.getElementById("llm-model-select").value,
          embedding_model: document.getElementById("embedding-model-select")
            .value,
          temperature: parseFloat(
            document.getElementById("temperature-slider").value
          ),
          theme: localStorage.getItem("theme") || "dark",
          font_size: localStorage.getItem("fontSize") || "medium",
          language: document.getElementById("language-select").value,
        };

        try {
          const response = await fetch("/api/settings/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(settings),
          });
          const data = await response.json();

          if (data.success) {
            showNotification(I18n.t("notifications.settingsSaved"), "success");

            // 保存成功后立即刷新当前配置显示和服务状态
            setTimeout(() => {
              refreshCurrentConfig();
              refreshServiceStatus();
            }, 500);
          } else {
            showNotification(
              data.message || I18n.t("notifications.loadingFailed"),
              "error"
            );
          }
        } catch (error) {
          showNotification(I18n.t("notifications.loadingFailed"), "error");
        }
      }

      // 恢复默认设置
      function resetSettings() {
        if (confirm("确定要恢复默认设置吗？")) {
          document.getElementById("api-key-input").value = "";
          document.getElementById("llm-model-select").value = "qwen-plus";
          document.getElementById("embedding-model-select").value =
            "text-embedding-v2";
          document.getElementById("temperature-slider").value = 0.7;
          document.getElementById("temperature-value").textContent = "0.7";
          document.getElementById("language-select").value = "zh-CN";

          setThemeFromSettings("dark");
          setFontSize("medium");

          showNotification(I18n.t("notifications.settingsReset"), "success");
        }
      }

      // 显示通知
      function showNotification(message, type = "info") {
        const notification = document.createElement("div");
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <span class="notification-text">${message}</span>
        `;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 14px 20px;
            background: ${
              type === "success"
                ? "rgba(34, 197, 94, 0.95)"
                : type === "error"
                ? "rgba(239, 68, 68, 0.95)"
                : "rgba(59, 130, 246, 0.95)"
            };
            color: white;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 500;
            z-index: 10000;
            animation: slideIn 0.3s ease;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        `;

        document.body.appendChild(notification);

        setTimeout(() => {
          notification.style.animation = "slideOut 0.3s ease forwards";
          setTimeout(() => notification.remove(), 300);
        }, 3000);
      }

      // 确认弹窗
      function showConfirmModal(title, message, onConfirm) {
        const overlay = document.createElement("div");
        overlay.className = "confirm-modal-overlay";
        overlay.innerHTML = `
          <div class="confirm-modal">
            <div class="confirm-modal-icon">
              <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
            </div>
            <h3 class="confirm-modal-title">${title}</h3>
            <p class="confirm-modal-message">${message}</p>
            <div class="confirm-modal-actions">
              <button class="confirm-modal-btn cancel">取消</button>
              <button class="confirm-modal-btn confirm">确认清空</button>
            </div>
          </div>
        `;
        document.body.appendChild(overlay);
        requestAnimationFrame(() => overlay.classList.add("active"));

        overlay.querySelector(".cancel").onclick = () => {
          overlay.classList.remove("active");
          setTimeout(() => overlay.remove(), 200);
        };
        overlay.querySelector(".confirm").onclick = () => {
          overlay.classList.remove("active");
          setTimeout(() => overlay.remove(), 200);
          onConfirm();
        };
        overlay.addEventListener("click", (e) => {
          if (e.target === overlay) {
            overlay.classList.remove("active");
            setTimeout(() => overlay.remove(), 200);
          }
        });
      }

      // 合同审查进度条
      const reviewSteps = [
        { label: "解析文档", desc: "识别合同文本结构..." },
        { label: "拆分条款", desc: "按条款逐段拆分分析..." },
        { label: "风险检测", desc: "对照法律法规检测风险..." },
        { label: "生成报告", desc: "汇总审查结果..." }
      ];

      function showReviewProgress() {
        let container = document.getElementById("review-progress");
        if (!container) {
          container = document.createElement("div");
          container.id = "review-progress";
          container.className = "review-progress";
          const inputBox = document.querySelector(".contract-panel .section-header");
          if (inputBox) inputBox.after(container);
        }
        container.innerHTML = `
          <div class="review-progress-inner">
            ${reviewSteps.map((s, i) => `
              <div class="review-step ${i === 0 ? 'active' : ''}" data-step="${i}">
                <div class="review-step-dot"></div>
                <div class="review-step-info">
                  <span class="review-step-label">${s.label}</span>
                  <span class="review-step-desc">${s.desc}</span>
                </div>
              </div>
            `).join('')}
          </div>
          <div class="review-progress-bar"><div class="review-progress-fill"></div></div>
        `;
        container.style.display = "block";
      }

      function updateReviewProgress(stepIndex) {
        const container = document.getElementById("review-progress");
        if (!container) return;
        const steps = container.querySelectorAll(".review-step");
        steps.forEach((el, i) => {
          el.classList.toggle("active", i === stepIndex);
          el.classList.toggle("done", i < stepIndex);
        });
        const fill = container.querySelector(".review-progress-fill");
        if (fill) {
          fill.style.width = `${((stepIndex + 1) / reviewSteps.length) * 100}%`;
        }
      }

      function hideReviewProgress() {
        const container = document.getElementById("review-progress");
        if (container) container.style.display = "none";
      }
      async function loadSettings() {
        try {
          const response = await fetch("/api/settings/load");
          const data = await response.json();

          if (data.success && data.settings) {
            const s = data.settings;
            if (s.api_key)
              document.getElementById("api-key-input").value = s.api_key;
            if (s.llm_model)
              document.getElementById("llm-model-select").value = s.llm_model;
            if (s.embedding_model)
              document.getElementById("embedding-model-select").value =
                s.embedding_model;
            if (s.temperature !== undefined) {
              document.getElementById("temperature-slider").value =
                s.temperature;
              document.getElementById("temperature-value").textContent =
                s.temperature;
            }
            if (s.language)
              document.getElementById("language-select").value = s.language;
          }
        } catch (error) {
          console.log("加载设置失败，使用默认值");
        }

        // 同步主题设置按钮状态
        const currentTheme = localStorage.getItem("theme") || "dark";
        document.querySelectorAll(".theme-option").forEach((btn) => {
          btn.classList.toggle("active", btn.dataset.theme === currentTheme);
        });

        // 同步字体大小设置
        const currentFontSize = localStorage.getItem("fontSize") || "medium";
        setFontSize(currentFontSize);
      }

      // 初始化设置页面
      function initSettingsPanel() {
        loadSettings();
        refreshServiceStatus();
        refreshCurrentConfig(); // 同时刷新当前生效的配置
      }

      // ===== 面板切换 =====
      let currentPanel = "welcome";
      let currentPredictionType = "analysis"; // 默认使用综合分析模式

      // ===== 对话历史管理（上下文记忆功能） =====
      let conversationHistory = []; // 存储当前会话的对话历史
      const MAX_HISTORY_LENGTH = 10; // 最大历史记录条数（防止上下文过长）

      const panelIcons = {
        welcome:
          '<svg viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9,22 9,12 15,12 15,22"/></svg>',
        qa: '<svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
        contract:
          '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
        case: '<svg viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22,4 12,14.01 9,11.01"/></svg>',
        laws: '<svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
        cases:
          '<svg viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
        settings:
          '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
      };

      // 面板标题翻译 key 映射
      const panelTitleKeys = {
        welcome: "nav.workspace",
        qa: "nav.qa",
        contract: "nav.contract",
        case: "nav.case",
        laws: "nav.laws",
        cases: "nav.cases",
        settings: "nav.settings",
      };

      function switchPanel(panelId) {
        document
          .querySelectorAll(".panel")
          .forEach((p) => p.classList.remove("active"));
        document.getElementById("panel-" + panelId).classList.add("active");

        document.querySelectorAll(".nav-item").forEach((item) => {
          item.classList.remove("active");
          if (item.dataset.panel === panelId) {
            item.classList.add("active");
          }
        });

        // 使用 I18n 获取翻译后的标题
        const titleKey = panelTitleKeys[panelId] || "nav.workspace";
        document.getElementById("page-title-text").textContent =
          I18n.t(titleKey);
        document.getElementById("page-icon").innerHTML =
          panelIcons[panelId] || panelIcons["welcome"];

        currentPanel = panelId;
      }

      document.querySelectorAll(".nav-item").forEach((item) => {
        item.addEventListener("click", () => {
          const panel = item.dataset.panel;
          if (panel) switchPanel(panel);
        });
      });

      // ===== 法律问答功能 =====
      const qaInput = document.getElementById("qa-input");
      const qaMessages = document.getElementById("qa-messages");

      qaInput.addEventListener("input", function () {
        this.style.height = "auto";
        this.style.height = Math.min(this.scrollHeight, 140) + "px";
      });

      qaInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          sendQuestion();
        }
      });

      function setQuestion(text) {
        qaInput.value = text;
        qaInput.focus();
        // 自动发送问题
        sendQuestion();
      }

      // 切换到消息视图
      function switchToMessageView() {
        const welcomeScreen = document.getElementById("qa-welcome-screen");
        const messagesArea = document.getElementById("qa-messages");
        const newChatBtn = document.getElementById("new-chat-btn");
        const quickQuestions = document.getElementById("quick-questions");
        const qaExamples = document.getElementById("qa-examples");

        if (welcomeScreen) welcomeScreen.style.display = "none";
        if (messagesArea) {
          messagesArea.classList.add("has-messages");
          messagesArea.style.display = "block";
        }
        if (newChatBtn) newChatBtn.style.display = "flex";
        if (quickQuestions) quickQuestions.style.display = "none";
        if (qaExamples) qaExamples.style.display = "none";
      }

      // 切换到欢迎视图
      function switchToWelcomeView() {
        const welcomeScreen = document.getElementById("qa-welcome-screen");
        const messagesArea = document.getElementById("qa-messages");
        const newChatBtn = document.getElementById("new-chat-btn");
        const quickQuestions = document.getElementById("quick-questions");
        const qaExamples = document.getElementById("qa-examples");

        if (welcomeScreen) welcomeScreen.style.display = "flex";
        if (messagesArea) {
          messagesArea.classList.remove("has-messages");
          messagesArea.style.display = "none";
          messagesArea.innerHTML = "";
        }
        if (newChatBtn) newChatBtn.style.display = "none";
        if (quickQuestions) quickQuestions.style.display = "flex";
        if (qaExamples) qaExamples.style.display = "flex";
      }

      // 开始新对话
      function startNewChat() {
        switchToWelcomeView();
        qaInput.value = "";
        qaInput.focus();
        // 清空对话历史
        conversationHistory = [];
        showNotification(I18n.t("qa.newChat"), "success");
      }

      async function sendQuestion() {
        const question = qaInput.value.trim();
        if (!question) return;

        // 切换到消息视图
        switchToMessageView();

        addMessage("user", question);
        qaInput.value = "";
        qaInput.style.height = "auto";

        const loadingId = addLoadingMessage();

        try {
          // 将当前问题添加到历史（用户消息）
          conversationHistory.push({
            role: "user",
            content: question,
          });

          // 限制历史长度，保留最近的对话
          if (conversationHistory.length > MAX_HISTORY_LENGTH * 2) {
            conversationHistory = conversationHistory.slice(
              -MAX_HISTORY_LENGTH * 2
            );
          }

          const response = await fetch("/api/qa/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              question,
              history: conversationHistory.slice(0, -1), // 发送当前问题之前的历史
            }),
          });

          if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.error || "请求失败");
          }

          // 移除加载动画，添加空的流式消息
          removeMessage(loadingId);
          const streamMsgId = addStreamingMessage();

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let fullAnswer = "";
          let sources = null;
          let buffer = "";

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            // 保留最后一个可能不完整的行
            buffer = lines.pop() || "";

            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              try {
                const data = JSON.parse(line.slice(6));

                if (data.type === "sources") {
                  sources = data.sources;
                } else if (data.type === "chunk") {
                  fullAnswer += data.content;
                  updateStreamingMessage(streamMsgId, fullAnswer);
                } else if (data.type === "done") {
                  finalizeStreamingMessage(streamMsgId, fullAnswer, sources);
                } else if (data.type === "error") {
                  throw new Error(data.message);
                }
              } catch (parseErr) {
                // 忽略解析错误，继续处理下一行
                if (parseErr.message && !parseErr.message.includes("JSON")) {
                  throw parseErr;
                }
              }
            }
          }

          // 将 AI 回复添加到历史
          conversationHistory.push({
            role: "assistant",
            content: fullAnswer,
          });
        } catch (err) {
          removeMessage(loadingId);
          addMessage("ai", "抱歉，服务暂时不可用，请稍后重试。");
          // 移除失败的用户消息历史
          conversationHistory.pop();
        }
      }

      // 流式消息辅助函数
      function addStreamingMessage() {
        const id = "stream-" + Date.now();
        const html = `
            <div class="message ai" id="${id}">
                <div class="message-inner">
                    <div class="message-avatar">法</div>
                    <div class="message-content">
                        <div class="message-bubble">
                            <div class="message-text"></div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        qaMessages.insertAdjacentHTML("beforeend", html);
        qaMessages.scrollTop = qaMessages.scrollHeight;
        return id;
      }

      function updateStreamingMessage(id, text) {
        const el = document.getElementById(id);
        if (!el) return;
        const textEl = el.querySelector(".message-text");
        if (!textEl) return;

        // 使用 marked.js 渲染 Markdown
        if (typeof marked !== "undefined") {
          marked.setOptions({
            breaks: true,
            gfm: true,
            headerIds: false,
            mangle: false,
          });
          textEl.innerHTML = marked.parse(text);
        } else {
          textEl.innerHTML = escapeHtml(text).replace(/\n/g, "<br>");
        }
        qaMessages.scrollTop = qaMessages.scrollHeight;
      }

      function finalizeStreamingMessage(id, text, sources) {
        const el = document.getElementById(id);
        if (!el) return;

        const sourceIcon =
          '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/></svg>';
        const webIcon =
          '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>';
        const copyIcon =
          '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
        const likeIcon =
          '<svg viewBox="0 0 24 24"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>';
        const dislikeIcon =
          '<svg viewBox="0 0 24 24"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/></svg>';

        const contentEl = el.querySelector(".message-content");

        // 添加来源信息
        if (sources && sources.length > 0) {
          const lawSources = sources.filter(s => !s.url);
          const webSources = sources.filter(s => s.url);
          let sourcesHtml = '<div class="message-sources"><div class="sources-title">参考来源</div><div class="sources-columns">';
          if (lawSources.length > 0) {
            sourcesHtml += `<div class="sources-col sources-col-law"><div class="sources-col-title">法律法规</div><div class="sources-list">${lawSources.map(s => `<span class="source-item">${escapeHtml(s.title || '法律条文')}</span>`).join('')}</div></div>`;
          }
          if (webSources.length > 0) {
            sourcesHtml += `<div class="sources-col sources-col-web"><div class="sources-col-title">网络检索</div><div class="sources-list">${webSources.map(s => `<a class="source-item" href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.title || '网页来源')}</a>`).join('')}</div></div>`;
          }
          sourcesHtml += '</div></div>';
          contentEl.insertAdjacentHTML("beforeend", sourcesHtml);
        }

        // 添加操作按钮
        const actionsHtml = `
            <div class="message-actions">
                <button class="action-btn" onclick="copyMessage('${id}')" title="复制回答">
                    ${copyIcon}
                </button>
                <button class="action-btn" onclick="likeMessage('${id}')" title="有帮助">
                    ${likeIcon}
                </button>
                <button class="action-btn" onclick="dislikeMessage('${id}')" title="无帮助">
                    ${dislikeIcon}
                </button>
            </div>
        `;
        contentEl.insertAdjacentHTML("beforeend", actionsHtml);
        qaMessages.scrollTop = qaMessages.scrollHeight;
      }

      function escapeHtml(str) {
        return String(str ?? "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#39;");
      }

      function addMessage(type, text, sources = null) {
        const id = "msg-" + Date.now();
        const avatarContent =
          type === "ai"
            ? "法"
            : '<svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';
        const sourceIcon =
          '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/></svg>';
        const webIcon =
          '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>';
        const copyIcon =
          '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
        const likeIcon =
          '<svg viewBox="0 0 24 24"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>';
        const dislikeIcon =
          '<svg viewBox="0 0 24 24"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/></svg>';

        // 使用 marked.js 渲染 Markdown（仅对 AI 回复进行渲染）
        let renderedText = text;
        if (type === "ai" && typeof marked !== "undefined") {
          // 配置 marked 选项
          marked.setOptions({
            breaks: true, // 支持换行符转换为 <br>
            gfm: true, // 启用 GitHub Flavored Markdown
            headerIds: false, // 禁用标题 ID
            mangle: false, // 禁用邮箱地址混淆
          });
          renderedText = marked.parse(text);
        } else {
          // 用户消息使用简单的换行处理
          renderedText = escapeHtml(text).replace(/\n/g, "<br>");
        }

        const messageHtml = `
            <div class="message ${type}" id="${id}">
                <div class="message-inner">
                    <div class="message-avatar">${avatarContent}</div>
                    <div class="message-content">
                        <div class="message-bubble">
                            <div class="message-text">${renderedText}</div>
                        </div>
                        ${
                          sources && sources.length > 0
                            ? (() => {
                                const lawSrcs = sources.filter(s => !s.url);
                                const webSrcs = sources.filter(s => s.url);
                                let html = '<div class="message-sources"><div class="sources-title">参考来源</div><div class="sources-columns">';
                                if (lawSrcs.length > 0) {
                                  html += `<div class="sources-col sources-col-law"><div class="sources-col-title">法律法规</div><div class="sources-list">${lawSrcs.map(s => `<span class="source-item">${escapeHtml(s.title || '法律条文')}</span>`).join('')}</div></div>`;
                                }
                                if (webSrcs.length > 0) {
                                  html += `<div class="sources-col sources-col-web"><div class="sources-col-title">网络检索</div><div class="sources-list">${webSrcs.map(s => `<a class="source-item" href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.title || '网页来源')}</a>`).join('')}</div></div>`;
                                }
                                html += '</div></div>';
                                return html;
                              })()
                            : ""
                        }
                        ${
                          type === "ai"
                            ? `
                            <div class="message-actions">
                                <button class="action-btn" onclick="copyMessage('${id}')" title="复制回答">
                                    ${copyIcon}
                                </button>
                                <button class="action-btn" onclick="likeMessage('${id}')" title="有帮助">
                                    ${likeIcon}
                                </button>
                                <button class="action-btn" onclick="dislikeMessage('${id}')" title="无帮助">
                                    ${dislikeIcon}
                                </button>
                            </div>
                        `
                            : ""
                        }
                    </div>
                </div>
            </div>
        `;
        qaMessages.insertAdjacentHTML("beforeend", messageHtml);
        qaMessages.scrollTop = qaMessages.scrollHeight;
        return id;
      }

      function copyMessage(id) {
        const msgEl = document.getElementById(id);
        if (msgEl) {
          const textEl = msgEl.querySelector(".message-text");
          if (textEl) {
            navigator.clipboard.writeText(textEl.innerText).then(() => {
              showNotification(I18n.t("notifications.copySuccess"), "success");
            });
          }
        }
      }

      function likeMessage(id) {
        showNotification(I18n.t("common.success"), "success");
      }

      function dislikeMessage(id) {
        showNotification(I18n.t("common.info"), "info");
      }

      function addLoadingMessage() {
        const id = "loading-" + Date.now();
        const html = `
            <div class="message ai" id="${id}">
                <div class="message-inner">
                    <div class="message-avatar">法</div>
                    <div class="message-content">
                        <div class="message-bubble">
                            <div class="typing-indicator">
                                <span class="typing-dot"></span>
                                <span class="typing-dot"></span>
                                <span class="typing-dot"></span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        qaMessages.insertAdjacentHTML("beforeend", html);
        qaMessages.scrollTop = qaMessages.scrollHeight;
        return id;
      }

      function removeMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
      }

      // ===== 合同审查功能 =====
      // 合同示例数据
      const contractSamples = [
        `劳动雇佣合同

甲方：科技无限公司
乙方：张三

第一条 工作时间与报酬
1.1 乙方承诺每天工作时间不低于12小时，每周工作7天。
1.2 乙方月薪为人民币5000元，包含所有加班费、社保补贴等，甲方不再额外支付任何费用。
1.3 若乙方因个人原因（包括生病）请假，甲方有权扣除当月全部工资。

第二条 保密与竞业限制
2.1 乙方在职期间及离职后10年内，不得在任何与甲方业务相关的企业任职，也不得自行从事相关业务。
2.2 若违反上述规定，乙方需支付违约金人民币100万元。

第三条 合同解除
3.1 甲方有权根据公司经营状况随时单方面解除本合同，且无需向乙方支付任何经济补偿金。
3.2 乙方若需辞职，必须提前6个月书面申请，否则需赔偿甲方招聘损失费5万元。

第四条 其他
4.1 本合同最终解释权归甲方所有。
4.2 发生争议时，双方只能向甲方所在地法院提起诉讼。`,

        `房屋租赁合同

出租方（甲方）：王某某
承租方（乙方）：李某某

第一条 房屋基本情况
甲方将位于北京市朝阳区某小区3号楼502室的房屋出租给乙方居住使用，建筑面积约80平方米。

第二条 租赁期限与租金
2.1 租赁期限为3年，自2024年1月1日至2026年12月31日。
2.2 月租金为人民币8000元，乙方须一次性支付全年租金，逾期一天按月租金10%支付滞纳金。
2.3 租赁期内，甲方有权根据市场行情随时调整租金，乙方须无条件接受。

第三条 押金与费用
3.1 乙方须支付押金人民币50000元，租赁期满后甲方有权以任何理由扣除押金。
3.2 房屋内所有设施的维修费用由乙方承担，包括因自然老化造成的损坏。

第四条 合同终止
4.1 甲方可提前7天通知乙方终止合同，无需说明理由，且不退还任何租金和押金。
4.2 乙方不得提前退租，如需提前退租，押金全部没收，且须支付剩余租期全部租金的50%作为违约金。

第五条 其他约定
5.1 乙方不得在房屋内养宠物、使用大功率电器，违者立即清退且不退还任何费用。
5.2 本合同解释权归甲方所有。`,

        `技术服务合同

委托方（甲方）：创新科技有限公司
受托方（乙方）：软件开发工作室

第一条 服务内容
乙方为甲方开发企业管理系统软件，包括但不限于用户管理、订单管理、库存管理等功能模块。

第二条 服务费用与支付
2.1 服务总费用为人民币200000元，甲方须在合同签订后3日内支付100%费用。
2.2 如甲方延迟付款，乙方有权暂停服务且不承担任何责任。
2.3 项目过程中的任何需求变更，甲方须额外支付变更费用，变更费用由乙方单方面确定。

第三条 知识产权
3.1 乙方开发的所有软件代码、技术文档、设计图纸等知识产权永久归乙方所有。
3.2 甲方仅获得软件的使用权，不得复制、修改、转让或进行反向工程。
3.3 合同终止后，甲方须立即停止使用该软件并删除所有副本。

第四条 保密义务
4.1 甲方须对乙方的技术秘密保密10年，违反保密义务须赔偿人民币500万元。
4.2 乙方对甲方的商业信息无保密义务。

第五条 违约责任
5.1 如乙方延期交付，每延期一天扣除服务费用的0.1%，累计扣除不超过5%。
5.2 如甲方延期验收超过7天，视为自动验收合格。
5.3 软件交付后出现的任何问题，乙方不承担任何责任。`,
      ];

      // 当前合同示例索引
      let currentContractSampleIndex = 0;

      function loadSampleContract() {
        // 确保先清除已上传的文件，避免冲突
        clearUploadedFile();

        document.getElementById("contract-original").value =
          contractSamples[currentContractSampleIndex];

        // 循环切换到下一个示例
        currentContractSampleIndex =
          (currentContractSampleIndex + 1) % contractSamples.length;
      }

      function clearContract() {
        showConfirmModal("确定要清空当前审查内容吗？", "此操作不可撤销，所有输入和审查结果将被清除。", () => {
          // 1. 重置输入框
          const textarea = document.getElementById("contract-original");
          if (textarea) {
            textarea.value = "";
            textarea.disabled = false;
            textarea.placeholder = "请在此粘贴需要审查的合同文本...";
          }

          // 2. 切换回输入模式
          const inputMode = document.getElementById("mode-input");
          const resultMode = document.getElementById("mode-result");
          if (inputMode) inputMode.style.display = "block";
          if (resultMode) resultMode.style.display = "none";

          // 3. 清空结果列表
          const clausesList = document.getElementById("clauses-list");
          const analysisList = document.getElementById("analysis-list");
          if (clausesList) clausesList.innerHTML = "";
          if (analysisList) analysisList.innerHTML = "";

          // 4. 重置风险统计
          ["high-risk-count", "medium-risk-count", "low-risk-count"].forEach(
            (id) => {
              const el = document.getElementById(id);
              if (el) el.textContent = "0";
            }
          );

          // 5. 清除上传文件状态
          clearUploadedFile();

          // 6. 重置按钮状态
          const btn = document.getElementById("review-btn");
          if (btn) {
            btn.innerHTML =
              '<svg viewBox="0 0 24 24"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg> 开始审查';
            btn.classList.remove("btn-danger");
            btn.disabled = false;
          }

          // 7. 重置控制器
          if (reviewAbortController) {
            reviewAbortController = null;
          }

          // 8. 隐藏进度条
          hideReviewProgress();

          // 9. 清除导出数据
          window.currentContractReviewData = null;

          showNotification("已清空审查内容", "success");
        });
      }

      // 文件上传相关函数
      function triggerFileUpload() {
        document.getElementById("contract-file-upload").click();
      }

      function handleFileUpload(input) {
        if (input.files && input.files[0]) {
          const file = input.files[0];
          document.getElementById("uploaded-filename").textContent = file.name;
          document.getElementById("file-upload-info").style.display = "flex";

          // 禁用文本输入框，避免混淆
          const textarea = document.getElementById("contract-original");
          textarea.value = ""; // 清空已有文本
          textarea.disabled = true;
          textarea.placeholder = "已选择文件，将对文件内容进行审查...";

          // 禁用加载示例按钮
          document.getElementById("btn-load-sample").disabled = true;
        }
      }

      function clearUploadedFile() {
        const input = document.getElementById("contract-file-upload");
        input.value = "";
        document.getElementById("file-upload-info").style.display = "none";
        document.getElementById("contract-original").disabled = false;
        document.getElementById("contract-original").placeholder =
          "请在此粘贴需要审查的合同文本...";

        // 启用加载示例按钮
        document.getElementById("btn-load-sample").disabled = false;
      }

      // 全局变量
      let reviewAbortController = null;

      async function reviewContract() {
        const btn = document.getElementById("review-btn");

        // 如果正在审查，则执行停止操作
        if (reviewAbortController) {
          // 通知后端取消，节省token
          if (window._reviewSessionId) {
            fetch(`/api/contract-review/cancel/${window._reviewSessionId}`, { method: 'POST' }).catch(() => {});
            window._reviewSessionId = null;
          }
          reviewAbortController.abort();
          reviewAbortController = null;
          return;
        }

        const fileInput = document.getElementById("contract-file-upload");
        const contractText = document
          .getElementById("contract-original")
          .value.trim();

        const hasFile = fileInput.files && fileInput.files.length > 0;

        if (!hasFile && !contractText) {
          alert("请输入需要审查的合同文本或上传合同文件");
          return;
        }

        // 初始化控制器
        reviewAbortController = new AbortController();

        // 更新按钮状态
        btn.innerHTML = '<span class="loading-spinner"></span> 停止审查';
        btn.classList.add("btn-danger");
        btn.disabled = false;

        // 显示进度条 - 第一步立即激活
        showReviewProgress();

        try {
          let fetchOptions = {
            method: "POST",
            signal: reviewAbortController.signal,
          };

          if (hasFile) {
            const formData = new FormData();
            formData.append("file", fileInput.files[0]);
            fetchOptions.body = formData;
          } else {
            fetchOptions.headers = { "Content-Type": "application/json" };
            fetchOptions.body = JSON.stringify({ contract_text: contractText });
          }

          const response = await fetch("/api/contract-review/stream", fetchOptions);

          if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.error || "请求失败");
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          let finalData = null;

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop();

            for (const line of lines) {
              if (line.startsWith("data: ")) {
                try {
                  const event = JSON.parse(line.slice(6));
                  if (event.type === "session") {
                    window._reviewSessionId = event.session_id;
                  } else if (event.type === "progress") {
                    updateReviewProgress(event.step);
                  } else if (event.type === "result") {
                    finalData = event.data;
                  } else if (event.type === "error") {
                    throw new Error(event.message);
                  }
                } catch (parseErr) {
                  if (parseErr.message && !parseErr.message.includes("JSON")) {
                    throw parseErr;
                  }
                }
              }
            }
          }

          if (finalData) {
            displayContractReview(finalData);
          } else {
            throw new Error("未收到审查结果");
          }
        } catch (err) {
          if (err.name === "AbortError") {
            console.log("审查已取消");
          } else {
            alert("审查失败：" + err.message);
          }
        } finally {
          hideReviewProgress();
          reviewAbortController = null;
          window._reviewSessionId = null;
          btn.innerHTML =
            '<svg viewBox="0 0 24 24"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg> 开始审查';
          btn.classList.remove("btn-danger");
          btn.disabled = false;
        }
      }

      async function exportContract() {
        if (!window.currentContractReviewData) {
          alert("请先进行合同审查，等待结果生成后再导出");
          return;
        }

        const btn = event.currentTarget; // 获取点击的按钮
        const originalContent = btn.innerHTML; // 保存原始按钮内容

        try {
          btn.innerHTML = '<span class="loading-spinner"></span> 正在导出...';
          btn.disabled = true;

          const response = await fetch("/api/export-contract-review", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify(window.currentContractReviewData),
          });

          if (!response.ok) {
            // 尝试解析 JSON 错误信息，如果不是 JSON 则抛出通用错误
            try {
              const data = await response.json();
              throw new Error(data.error || "导出失败");
            } catch (e) {
              // 如果是 JSON 解析错误，说明返回的不是 JSON (可能是 HTML 错误页)
              if (e.name === "SyntaxError") {
                throw new Error(
                  `服务器错误 (${response.status}): 请检查后端服务是否重启`
                );
              }
              throw e;
            }
          }

          // 处理文件下载
          const blob = await response.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;

          // 优化文件名：使用原始文件名（如果存在）或当前日期
          let filename = "contract_review_report.zip";
          if (
            window.currentContractReviewData &&
            window.currentContractReviewData.original_filename
          ) {
            const originalName =
              window.currentContractReviewData.original_filename.replace(
                /\.[^/.]+$/,
                ""
              );
            filename = `合同审查报告_${originalName}.zip`;
          } else {
            const dateStr = new Date().toISOString().slice(0, 10);
            filename = `合同审查报告_${dateStr}.zip`;
          }

          a.download = filename;
          document.body.appendChild(a);
          a.click();
          window.URL.revokeObjectURL(url);
          document.body.removeChild(a);
        } catch (err) {
          console.error("导出失败:", err);
          alert("导出失败: " + err.message);
        } finally {
          btn.innerHTML = originalContent;
          btn.disabled = false;
        }
      }

      // 交互高亮函数
      function highlightRight(analysisId) {
        const target = document.getElementById(analysisId);
        if (target) {
          target.classList.add("active");
          target.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }
      function unhighlightRight(analysisId) {
        const target = document.getElementById(analysisId);
        if (target) target.classList.remove("active");
      }

      function highlightLeft(clauseId) {
        const target = document.getElementById(clauseId);
        if (target) {
          target.classList.add("active");
          target.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }
      function unhighlightLeft(clauseId) {
        const target = document.getElementById(clauseId);
        if (target) target.classList.remove("active");
      }

      function switchContractView(viewType) {
        console.log("Switching view to:", viewType);

        // 1. 更新按钮状态
        document.querySelectorAll(".view-btn").forEach((btn) => {
          btn.classList.toggle("active", btn.dataset.view === viewType);
        });

        // 2. 更新内容显示 (回归最简单的 class 切换)
        document.querySelectorAll(".clause-content").forEach((el) => {
          el.classList.remove("active");
          if (el.classList.contains(viewType)) {
            el.classList.add("active");
          }
        });
      }

      function displayContractReview(data) {
        console.log("Displaying contract review", data);
        window.currentContractReviewData = data; // Store data for export
        const clauses = data.clauses_analysis || [];

        // === 辅助函数：处理包含 HTML 的文本内容 ===
        // 解码可能被转义的 HTML 实体，确保表格等 HTML 元素能正确渲染
        function processHtmlContent(text) {
          if (!text) return "";

          // 检查是否包含转义的 HTML 实体
          if (text.includes("&lt;") || text.includes("&gt;")) {
            const textarea = document.createElement("textarea");
            textarea.innerHTML = text;
            text = textarea.value;
          }

          // 处理 Markdown 格式的表格，转换为 HTML 表格
          if (text.includes("|") && text.includes("---")) {
            text = convertMarkdownTableToHtml(text);
          }

          return text;
        }

        // === 辅助函数：将 Markdown 表格转换为 HTML 表格 ===
        function convertMarkdownTableToHtml(text) {
          const lines = text.split("\n");
          let result = [];
          let tableLines = [];
          let inTable = false;

          for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();

            // 检测是否是表格行（以 | 开头和结尾，或至少包含 |）
            const isTableRow = line.startsWith("|") && line.endsWith("|");
            const isSeparatorRow = /^\|[\s\-:|]+\|$/.test(line);

            if (isTableRow || isSeparatorRow) {
              if (!inTable) {
                inTable = true;
              }
              tableLines.push(line);
            } else {
              if (inTable && tableLines.length > 0) {
                // 将收集的表格行转换为 HTML
                result.push(parseMarkdownTable(tableLines));
                tableLines = [];
                inTable = false;
              }
              result.push(line);
            }
          }

          // 处理文件末尾的表格
          if (tableLines.length > 0) {
            result.push(parseMarkdownTable(tableLines));
          }

          return result.join("\n");
        }

        function parseMarkdownTable(lines) {
          if (lines.length < 2) return lines.join("\n");

          let html = "<table>";
          let headerProcessed = false;

          for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();

            // 跳过分隔行
            if (/^\|[\s\-:|]+\|$/.test(line)) continue;

            const cells = line
              .split("|")
              .filter((cell, idx, arr) => idx > 0 && idx < arr.length - 1);

            if (!headerProcessed) {
              html += "<thead><tr>";
              cells.forEach((cell) => {
                html += `<th>${cell.trim()}</th>`;
              });
              html += "</tr></thead><tbody>";
              headerProcessed = true;
            } else {
              html += "<tr>";
              cells.forEach((cell) => {
                html += `<td>${cell.trim()}</td>`;
              });
              html += "</tr>";
            }
          }

          html += "</tbody></table>";
          return html;
        }

        // 1. 更新风险统计
        let highRisk = 0,
          mediumRisk = 0,
          lowRisk = 0;
        clauses.forEach((c) => {
          const level = (c.risk_level || "").toLowerCase();
          if (level.includes("高") || level.includes("high")) highRisk++;
          else if (level.includes("中") || level.includes("medium"))
            mediumRisk++;
          else lowRisk++;
        });

        const highRiskEl = document.getElementById("high-risk-count");
        const mediumRiskEl = document.getElementById("medium-risk-count");
        const lowRiskEl = document.getElementById("low-risk-count");

        if (highRiskEl) highRiskEl.textContent = highRisk;
        if (mediumRiskEl) mediumRiskEl.textContent = mediumRisk;
        if (lowRiskEl) lowRiskEl.textContent = lowRisk;

        // 2. 切换视图模式
        const inputMode = document.getElementById("mode-input");
        const resultMode = document.getElementById("mode-result");
        if (inputMode) inputMode.style.display = "none";
        if (resultMode) resultMode.style.display = "block";

        // 3. 生成 HTML
        let contractHtml = "";
        let analysisHtml = "";
        let lastSection = null;

        clauses.forEach((clause, index) => {
          const clauseId = `clause-${index}`;
          const analysisId = `analysis-${index}`;
          const sectionTitle = clause.section || "";

          // 插入章节标题
          if (
            sectionTitle &&
            sectionTitle !== lastSection &&
            sectionTitle !== "自动分割"
          ) {
            contractHtml += `<div class="section-header" style="font-weight: 600; font-size: 1.1em; margin: 16px 0 8px 0; color: var(--text-primary); border: none; padding-bottom: 8px;">${sectionTitle}</div>`;
            lastSection = sectionTitle;
          }

          // === 关键修复：确保文本存在 ===
          // 尝试从多个字段获取文本
          let rawText =
            clause.clause_text || clause.content || clause.text || "";
          if (!rawText && clause.clause_number) {
            // 如果真的没有文本，显示占位符以便调试
            rawText = `[条款 ${clause.clause_number} 内容缺失]`;
            console.warn("Clause text missing for:", clause);
          }

          // === 处理 HTML/Markdown 内容，确保表格等元素正确渲染 ===
          const originalText = processHtmlContent(rawText);
          const redlineText = processHtmlContent(clause.diff_html || rawText);
          const revisedText = processHtmlContent(
            clause.revised_text || rawText
          );

          // 特殊处理：如果是首部或尾部，不显示序号，且居中显示
          const isHeaderOrFooter =
            clause.type === "首部" ||
            clause.type === "尾部" ||
            clause.type === "Header" ||
            clause.type === "Footer";
          const numberDisplay = isHeaderOrFooter
            ? ""
            : clause.clause_number || index + 1;
          // 关键修复：普通条款不设置内联样式，完全由 CSS (.clause-body) 控制，以便您在 CSS 中调整 top 值
          const contentStyle = isHeaderOrFooter
            ? "font-weight: bold; text-align: center; padding: 10px 0;"
            : "";

          // 构建HTML - 恢复标准结构，依赖 CSS 类控制
          contractHtml += `
                <div id="${clauseId}" class="clause-text-block" 
                     onmouseenter="highlightRight('${analysisId}')"
                     onmouseleave="unhighlightRight('${analysisId}')">
                    <div class="clause-number">${numberDisplay}</div>
                    <div class="clause-body" style="${contentStyle}">
                        <div class="clause-content original active">${originalText}</div>
                        <div class="clause-content redline">${redlineText}</div>
                        <div class="clause-content revised">${revisedText}</div>
                    </div>
                </div>
            `;

          // 右侧：分析卡片 (保持不变)
          const riskLevel = clause.risk_level || "Unknown";

          // 优化分析文本：
          // 1. 移除重复的"风险等级：XXX"
          // 2. 格式化"问题"和"建议"
          let analysisText = clause.analysis || "";

          // 移除开头的风险等级描述
          analysisText = analysisText.replace(/^风险等级：.*?\n/, "");

          // 格式化问题和建议
          // 将风险标签插入到"问题："的上一行右侧
          // 我们使用 flex 布局来实现这一点，将标签放在一个独立的 div 中，位于问题之前

          // 确定风险徽章样式
          let badgeClass = "risk-badge";
          if (riskLevel.includes("中") || riskLevel.includes("Medium")) {
            badgeClass += " medium";
          } else if (riskLevel.includes("低") || riskLevel.includes("Low")) {
            badgeClass += " low";
          }

          // 优化布局：将徽章放在"问题"的上一行，且靠右显示
          // 【在此处调整】margin-right 控制标签距离右侧边缘的距离。负值（如 -12px）可以抵消容器的 padding，使其更靠右。
          const riskBadgeHtml = `<div style="display: flex; justify-content: flex-end; margin-bottom: 2px; margin-right: 5px;"><span class="${badgeClass}">${riskLevel}</span></div>`;

          analysisText = analysisText
            .replace(
              /问题：/g,
              `${riskBadgeHtml}<div style="margin-bottom: 6px;"><strong style="color: var(--accent-danger);">问题：</strong>`
            )
            .replace(
              /建议：/g,
              '</div><div style="margin-top: 8px; margin-bottom: 4px;"><strong style="color: var(--accent-success);">建议：</strong></div>'
            )
            .replace(/\n/g, "<br>");

          // 确保闭合 div
          if (analysisText.includes("建议：")) {
            analysisText += "</div>";
          }

          let evidenceHtml = "";
          if (clause.evidence && clause.evidence.length > 0) {
            evidenceHtml = clause.evidence
              .map((ev) => {
                // 修复：处理 Windows 路径分隔符，只显示文件名
                const sourceName = ev.source
                  ? ev.source
                      .replace(/\\/g, "/")
                      .split("/")
                      .pop()
                      .replace(".md", "")
                  : "未知来源";
                return `
                        <div class="evidence-item">
                            <span class="evidence-source">${sourceName}</span>
                            <div class="evidence-text">${ev.content}</div>
                        </div>
                    `;
              })
              .join("");
          } else {
            evidenceHtml = `<div class="evidence-text" style="font-style: italic;">${
              clause.related_laws || "未检索到具体法条"
            }</div>`;
          }

          analysisHtml += `
                <div id="${analysisId}" class="analysis-card"
                     onmouseenter="highlightLeft('${clauseId}')"
                     onmouseleave="unhighlightLeft('${clauseId}')">
                    <!-- 移除独立的 header，标签已移入 content -->
                    <div class="analysis-content">${analysisText}</div>
                    <div class="evidence-panel">
                        <div class="evidence-title">📚 法律依据</div>
                        ${evidenceHtml}
                    </div>
                </div>
            `;
        });

        // 4. 注入 DOM
        const clausesList = document.getElementById("clauses-list");
        const analysisList = document.getElementById("analysis-list");

        if (clausesList) clausesList.innerHTML = contractHtml;
        if (analysisList) analysisList.innerHTML = analysisHtml;

        // 5. 默认显示红线视图
        switchContractView("redline");
      }

      // ===== 案情预测功能 =====
      function selectPredictionType(btn) {
        document
          .querySelectorAll(".prediction-btn")
          .forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentPredictionType = btn.dataset.type;
      }

      // 案例示例数据
      const caseSamples = [
        `2023年5月，被告人王某在某市A区驾驶机动车时，因超速行驶且闯红灯，与一辆正常行驶的电动自行车发生碰撞，导致电动自行车驾驶人李某当场死亡。经交警部门认定，王某负事故全部责任。事故发生后，王某未逃逸，主动报警并在现场等待处理。王某曾有一次酒驾记录，但此次事故时未饮酒。案发后，王某家属积极赔偿被害人家属损失共计人民币80万元，取得了被害人家属的谅解。王某系初犯，归案后如实供述犯罪事实，认罪态度较好。`,

        `2024年3月，被告人张某因与邻居陈某存在土地纠纷积怨已久。某日，双方再次发生争吵，张某情绪失控，持菜刀将陈某砍伤。经法医鉴定，陈某所受伤害为轻伤二级。案发后，张某主动投案自首，如实供述犯罪事实。张某家属已赔偿陈某医疗费等各项损失共计人民币5万元，并取得陈某的书面谅解。张某系初犯、偶犯，无前科劣迹，平时表现良好，系本村村民代表。`,

        `2023年11月，被告人刘某担任某公司财务经理期间，利用职务便利，采用伪造财务凭证、虚列支出等手段，先后10次侵占公司资金共计人民币120万元，用于个人购买房产和炒股。经查，刘某在公司任职5年，此前工作表现正常，无违法违纪记录。案发后，刘某的家属代为退还全部赃款120万元，刘某归案后如实供述了全部犯罪事实，自愿认罪认罚。公司出具了谅解书，表示不再追究刘某的民事责任。`,
      ];

      // 当前案例示例索引
      let currentCaseSampleIndex = 0;

      function loadSampleCase() {
        document.getElementById("case-fact").value =
          caseSamples[currentCaseSampleIndex];

        // 循环切换到下一个示例
        currentCaseSampleIndex =
          (currentCaseSampleIndex + 1) % caseSamples.length;
      }

      async function predictCase() {
        const caseFact = document.getElementById("case-fact").value.trim();
        if (!caseFact) {
          alert("请输入案情描述");
          return;
        }

        const btn = document.querySelector(".input-box .btn-primary");
        btn.innerHTML = '<span class="loading-spinner"></span> 分析中...';
        btn.disabled = true;

        try {
          let endpoint = "/api/case/imprisonment";
          if (currentPredictionType === "accusation") {
            endpoint = "/api/case/accusation";
          } else if (currentPredictionType === "analysis") {
            endpoint = "/api/case/analysis";
          }

          const response = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query_fact: caseFact }),
          });
          const data = await response.json();

          displayPredictionResults(data);
        } catch (err) {
          alert("预测失败：" + err.message);
        } finally {
          btn.innerHTML =
            '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polygon points="10,8 16,12 10,16" fill="currentColor" stroke="none"/></svg> <span data-i18n="case.startAnalysis">开始智能分析</span>';
          btn.disabled = false;
        }
      }

      // 存储当前分析数据用于导出
      let currentAnalysisData = null;

      function displayPredictionResults(data) {
        // 保存数据用于导出
        currentAnalysisData = data;

        const resultsEl = document.getElementById("prediction-results");
        const analysisEl = document.getElementById("analysis-section");

        // 显示摘要卡片
        resultsEl.style.display = "flex";
        resultsEl.style.animation = "none";
        resultsEl.offsetHeight;
        resultsEl.style.animation = "summaryFadeIn 0.5s ease-out";

        // 填充罪名推测
        const crimeEl = document.getElementById("predicted-crime");
        if (data.predicted_accusation) {
          crimeEl.textContent = data.predicted_accusation;
        } else if (data.structured_prediction && data.structured_prediction.crime) {
          crimeEl.textContent = data.structured_prediction.crime;
        } else if (data.accusation_distribution) {
          const top = Object.entries(data.accusation_distribution).sort((a, b) => b[1] - a[1]);
          crimeEl.textContent = top.length > 0 ? top[0][0] : "--";
        } else {
          crimeEl.textContent = "--";
        }

        // 填充刑期区间
        const rangeEl = document.getElementById("predicted-range");
        if (data.case_statistics) {
          const stats = data.case_statistics;
          rangeEl.textContent = `${Math.round(stats.min)}-${Math.round(stats.max)} 个月`;
        } else if (data.predicted_imprisonment !== undefined) {
          rangeEl.textContent = `${data.predicted_imprisonment} 个月`;
        } else {
          rangeEl.textContent = "--";
        }

        analysisEl.style.display = "block";
        analysisEl.style.animation = "none";
        analysisEl.offsetHeight;
        analysisEl.style.animation = "reportSlideUp 0.5s ease-out";

        // 设置时间戳
        const now = new Date();
        const timestamp = `${now.getFullYear()}年${
          now.getMonth() + 1
        }月${now.getDate()}日 ${now
          .getHours()
          .toString()
          .padStart(2, "0")}:${now.getMinutes().toString().padStart(2, "0")}`;
        document.getElementById("report-timestamp").textContent = timestamp;

        // 使用 marked.js 渲染 Markdown 内容
        const aiResponse = data.ai_response || "暂无分析结果";
        const lawContext = data.law_context || "";
        const similarCasesText = data.similar_cases_text || "";

        // 渲染 Markdown 为 HTML
        let renderedContent = "";
        try {
          if (typeof marked !== "undefined" && marked.parse) {
            renderedContent = marked.parse(aiResponse);
          } else {
            // 简单的Markdown渲染后备方案
            renderedContent = simpleMarkdownRender(aiResponse);
          }
        } catch (e) {
          renderedContent = simpleMarkdownRender(aiResponse);
        }

        document.getElementById("analysis-content").innerHTML = renderedContent;

        // 处理相关案例分析
        const caseSection = document.getElementById("case-reference-section");
        const caseContent = document.getElementById("case-reference-content");

        if (data.similar_cases_data && data.similar_cases_data.length > 0) {
          const renderedCases = renderSimilarCasesFromData(
            data.similar_cases_data
          );
          caseSection.style.display = "block";
          caseContent.innerHTML = renderedCases;
          bindCaseCardClicks();
        } else if (similarCasesText && similarCasesText.trim()) {
          const renderedCases = renderSimilarCasesStructured(similarCasesText);
          caseSection.style.display = "block";
          caseContent.innerHTML = renderedCases;
          bindCaseCardClicks();
        } else {
          caseSection.style.display = "none";
        }

        // 处理法律依据
        const lawSection = document.getElementById("law-reference-section");
        const lawContent = document.getElementById("law-reference-content");

        if (lawContext && lawContext.trim()) {
          lawSection.style.display = "block";
          // 格式化法律条文
          lawContent.innerHTML = formatLawContext(lawContext);
        } else {
          lawSection.style.display = "none";
        }

        // 平滑滚动到结果区域
        setTimeout(() => {
          resultsEl.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 100);
      }

      // 绑定案例卡片点击，弹出详情
      function bindCaseCardClicks() {
        const cards = document.querySelectorAll(".case-ref-card.clickable");
        cards.forEach((card) => {
          card.onclick = () => {
            const title = card.dataset.title || "案例详情";
            const body = decodeURIComponent(card.dataset.body || "");
            showCaseModal(title, body);
          };
        });
      }

      function showCaseModal(title, body) {
        const mask = document.getElementById("case-modal-mask");
        const titleEl = document.getElementById("case-modal-title");
        const bodyEl = document.getElementById("case-modal-body");
        if (!mask || !titleEl || !bodyEl) return;
        titleEl.textContent = title;
        bodyEl.innerHTML = (body || "")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/\n/g, "<br>");
        mask.style.display = "flex";
      }

      function hideCaseModal() {
        const mask = document.getElementById("case-modal-mask");
        if (mask) mask.style.display = "none";
      }

      // 渲染结构化的相似案例（优先使用）
      function renderSimilarCasesFromData(cases) {
        if (!cases || !cases.length) return "";

        const escape = (s) =>
          String(s || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        const html = cases
          .map((c) => {
            const badgesList =
              c.badges && c.badges.length
                ? c.badges
                    .map(
                      (b) => `<span class="case-ref-badge">${escape(b)}</span>`
                    )
                    .join("")
                : "";

            // 底部元数据区域：包含标签（左）和查看详情（右）
            const footer = `
              <div class="case-ref-meta">
                <div class="case-ref-badges-wrap">
                  ${badgesList}
                </div>
                <div class="case-ref-action">
                  查看详情
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                </div>
              </div>
            `;

            const dataTitle = `案例${escape(c.no)}｜${escape(
              c.title || "相似案例"
            )}`;
            // 完整内容用于弹窗
            const dataBody = encodeURIComponent(c.body || "");

            // 卡片显示内容（截断）
            let displayBody = c.body || "";
            if (displayBody.length > 200) {
              displayBody = displayBody.substring(0, 200) + "...";
            }

            return `
              <div class="case-ref-card clickable" data-title="${dataTitle}" data-body="${dataBody}">
                <div class="case-ref-header">
                  <div class="case-ref-no">案例${escape(c.no)}</div>
                  <div class="case-ref-title">${escape(
                    c.title || "相似案例"
                  )}</div>
                </div>
                <div class="case-ref-body">${escape(displayBody).replace(
                  /\n/g,
                  "<br>"
                )}</div>
                ${footer}
              </div>
            `;
          })
          .join("");
        return `<div class="case-ref-list">${html}</div>`;
      }

      // 解析并渲染相似案例（网页端，不截断）
      function renderSimilarCasesStructured(text) {
        const cases = parseSimilarCases(text);
        if (!cases.length) {
          return simpleMarkdownRender(text);
        }

        const escape = (s) =>
          String(s || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        const html = cases
          .map((c) => {
            const badgesList =
              c.badges && c.badges.length
                ? c.badges
                    .map(
                      (b) => `<span class="case-ref-badge">${escape(b)}</span>`
                    )
                    .join("")
                : "";

            // 底部元数据区域
            const footer = `
              <div class="case-ref-meta">
                <div class="case-ref-badges-wrap">
                  ${badgesList}
                </div>
                <div class="case-ref-action">
                  查看详情
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                </div>
              </div>
            `;

            const dataTitle = `案例${escape(c.no)}｜${escape(
              c.title || "相似案例"
            )}`;
            const dataBody = encodeURIComponent(c.body || "");
            return `
              <div class="case-ref-card clickable" data-title="${dataTitle}" data-body="${dataBody}">
                <div class="case-ref-header">
                  <div class="case-ref-no">案例${escape(c.no)}</div>
                  <div class="case-ref-title">${escape(
                    c.title || "相似案例"
                  )}</div>
                </div>
                <div class="case-ref-body">${escape(c.body).replace(
                  /\n/g,
                  "<br>"
                )}</div>
                ${footer}
              </div>
            `;
          })
          .join("");
        return `<div class="case-ref-list">${html}</div>`;
      }

      // 解析并渲染相似案例（PDF端，不截断）
      function renderSimilarCasesForPDF(text) {
        const cases = parseSimilarCases(text);
        if (!cases.length) {
          return simpleMarkdownRender(text);
        }
        const escape = (s) =>
          String(s || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        const html = cases
          .map((c) => {
            const badges =
              c.badges && c.badges.length
                ? `<div class="pdf-case-meta">${c.badges
                    .map(
                      (b) => `<span class="pdf-case-tag">${escape(b)}</span>`
                    )
                    .join("")}</div>`
                : "";

            return `
              <div class="pdf-case-item">
                <div class="pdf-case-title">案例${escape(c.no)}｜${escape(
              c.title || "相似案例"
            )}</div>
                <div class="pdf-case-body">${escape(c.body).replace(
                  /\n/g,
                  "<br>"
                )}</div>
                ${badges}
              </div>
            `;
          })
          .join("");
        return `<div class="pdf-case-list">${html}</div>`;
      }

      // 基础解析，将案例文本拆分为结构化数据（不截断）
      function parseSimilarCases(text) {
        if (!text || !text.trim()) return [];
        const blocks = text.split(/\n\n+/).filter((b) => b.trim());
        return blocks.map((block, idx) => {
          const lines = block.split("\n").filter((l) => l.trim());
          const header = lines[0] || `案例${idx + 1}`;
          const headerMatch = header.match(/^案例\s*(\d+)\s*[|｜\\|]?\s*(.*)$/);
          const no = headerMatch ? headerMatch[1] || idx + 1 : idx + 1;
          const title =
            headerMatch && headerMatch[2]
              ? headerMatch[2].trim()
              : header.trim();

          let bodyLines = lines.slice(1);
          if (bodyLines.length === 0) bodyLines = lines;

          const badges = [];
          const filteredBodyLines = [];

          bodyLines.forEach((l) => {
            const trimmed = l.trim();
            if (/^(量刑情节|判决|裁判)[:：]/.test(trimmed)) {
              badges.push(trimmed);
            } else {
              filteredBodyLines.push(l);
            }
          });

          return {
            no,
            title,
            body: filteredBodyLines.join("\n").trim() || "",
            badges,
          };
        });
      }

      // 简单的Markdown渲染（后备方案）
      function simpleMarkdownRender(text) {
        return (
          text
            // 标题
            .replace(/^#### (.+)$/gm, "<h4>$1</h4>")
            .replace(/^### (.+)$/gm, "<h3>$1</h3>")
            .replace(/^## (.+)$/gm, "<h2>$1</h2>")
            .replace(/^# (.+)$/gm, "<h1>$1</h1>")
            // 加粗
            .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
            // 斜体
            .replace(/\*(.+?)\*/g, "<em>$1</em>")
            // 列表
            .replace(/^- (.+)$/gm, "<li>$1</li>")
            // 换行
            .replace(/\n\n/g, "</p><p>")
            .replace(/\n/g, "<br>")
            // 包装段落
            .replace(/^(.+)$/gm, (match) => {
              if (
                match.startsWith("<h") ||
                match.startsWith("<li") ||
                match.startsWith("<p")
              )
                return match;
              return match;
            })
        );
      }

      // 格式化法律条文
      function formatLawContext(lawContext) {
        // 分割各条法律
        const articles = lawContext.split(
          /(?=第[一二三四五六七八九十百千万零〇\d]+条)/
        );

        let html = "";
        articles.forEach((article) => {
          const trimmed = article.trim();
          if (!trimmed) return;

          // 提取条文标题（如 "第七十六条"）
          const titleMatch = trimmed.match(
            /^(第[一二三四五六七八九十百千万零〇\d]+条[^\n]*)/
          );
          if (titleMatch) {
            const title = titleMatch[1];
            const content = trimmed.substring(title.length).trim();
            html += `
              <div class="law-article">
                <div class="law-article-title">${title}</div>
                <div class="law-article-content">${content}</div>
              </div>
            `;
          } else {
            html += `<div class="law-article"><div class="law-article-content">${trimmed}</div></div>`;
          }
        });

        return html || `<div class="law-article-content">${lawContext}</div>`;
      }

      // PDF导出功能 - 优先使用前端生成以获得更好的样式控制
      async function exportReportToPDF() {
        if (!currentAnalysisData) {
          alert("没有可导出的分析报告");
          return;
        }

        const btn = document.querySelector(".btn-export");
        const originalText = btn.innerHTML;
        btn.innerHTML = '<span class="loading-spinner"></span> 生成中...';
        btn.disabled = true;

        try {
          // 优先使用前端生成PDF（样式更专业）
          await exportReportAsPDFClientSide();
        } catch (err) {
          console.error("PDF生成失败:", err);
          alert("PDF生成失败，请稍后重试");
        } finally {
          btn.innerHTML = originalText;
          btn.disabled = false;
        }
      }

      // 前端PDF生成回退方案：jsPDF + html2canvas（直接下载PDF，不走浏览器打印，避免页脚URL/乱码）
      async function exportReportAsPDFClientSide() {
        if (!currentAnalysisData) return;

        if (!window.html2canvas || !window.jspdf || !window.jspdf.jsPDF) {
          alert("前端PDF组件未加载，请稍后重试或检查网络（CDN）。");
          return;
        }

        const caseFact = document.getElementById("case-fact").value.trim();
        const now = new Date();
        const dateStr = `${now.getFullYear()}年${
          now.getMonth() + 1
        }月${now.getDate()}日`;
        const timeStr = `${now.getHours().toString().padStart(2, "0")}:${now
          .getMinutes()
          .toString()
          .padStart(2, "0")}`;

        // 创建离屏容器渲染内容
        const pdfContainer = document.createElement("div");
        pdfContainer.id = "pdf-export-container";
        pdfContainer.style.cssText = `
          position: fixed;
          left: -99999px;
          top: 0;
          width: 794px;
          background: #ffffff;
          font-family: "Noto Serif SC", "Source Han Serif SC", "Microsoft YaHei", "SimSun", serif;
          font-size: 14px;
          line-height: 1.75;
          color: #1a1a2e;
          z-index: -1;
        `;

        const analysisHTML =
          document.getElementById("analysis-content")?.innerHTML || "";
        const lawHTML =
          document.getElementById("law-reference-content")?.innerHTML || "";
        const caseHTMLForPDF = renderSimilarCasesForPDF(
          currentAnalysisData.similar_cases_text || ""
        );

        const statsRange = currentAnalysisData.case_statistics
          ? `${Math.round(
              currentAnalysisData.case_statistics.min
            )}-${Math.round(currentAnalysisData.case_statistics.max)}`
          : "--";

        // 专业PDF样式 - 精炼、沉稳、专业
        const pdfStyles = `
          <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            
            .pdf-wrapper {
              padding: 52px 60px;
              min-height: 100%;
              background: #fff;
            }
            
            /* 页眉 - 简洁专业 */
            .pdf-header {
              display: flex;
              align-items: center;
              justify-content: space-between;
              padding-bottom: 18px;
              margin-bottom: 32px;
              border-bottom: 2px solid #1a365d;
            }
            .pdf-header-left {
              display: flex;
              align-items: center;
              gap: 16px;
            }
            .pdf-logo {
              width: 44px;
              height: 44px;
              background: #1a365d;
              border-radius: 6px;
              display: flex;
              align-items: center;
              justify-content: center;
              color: #fff;
              font-size: 13px;
              font-weight: 700;
              letter-spacing: 1px;
            }
            .pdf-brand-name {
              font-size: 22px;
              font-weight: 700;
              color: #1a365d;
              letter-spacing: 3px;
            }
            .pdf-header-right {
              text-align: right;
              color: #64748b;
              font-size: 12px;
              line-height: 1.6;
            }
            
            /* 标题区 */
            .pdf-title-section {
              text-align: center;
              margin-bottom: 36px;
              padding: 32px 24px;
              background: #f8fafc;
              border: 1px solid #e2e8f0;
              border-radius: 8px;
            }
            .pdf-main-title {
              font-size: 26px;
              font-weight: 700;
              color: #0f172a;
              letter-spacing: 4px;
              margin-bottom: 12px;
            }
            .pdf-title-line {
              width: 48px;
              height: 2px;
              background: #b8860b;
              margin: 0 auto 14px;
            }
            .pdf-title-sub {
              font-size: 13px;
              color: #64748b;
              letter-spacing: 1px;
            }
            
            /* 核心指标 */
            .pdf-metrics {
              display: flex;
              gap: 20px;
              margin-bottom: 36px;
            }
            .pdf-metric {
              flex: 1;
              background: #fff;
              border: 1px solid #e2e8f0;
              border-top: 3px solid #b8860b;
              border-radius: 6px;
              padding: 20px 16px;
              text-align: center;
            }
            .pdf-metric.type-b { border-top-color: #3b82f6; }
            .pdf-metric.type-c { border-top-color: #10b981; }
            .pdf-metric-label {
              font-size: 11px;
              color: #64748b;
              text-transform: uppercase;
              letter-spacing: 1.5px;
              margin-bottom: 8px;
            }
            .pdf-metric-value {
              font-size: 36px;
              font-weight: 700;
              color: #0f172a;
              line-height: 1;
            }
            .pdf-metric-unit {
              font-size: 12px;
              color: #94a3b8;
              margin-top: 6px;
            }
            
            /* 内容分节 */
            .pdf-section {
              margin-bottom: 28px;
              page-break-inside: avoid;
            }
            .pdf-section-head {
              display: flex;
              align-items: center;
              gap: 12px;
              margin-bottom: 14px;
              padding-bottom: 10px;
              border-bottom: 1px solid #e2e8f0;
            }
            .pdf-section-num {
              width: 28px;
              height: 28px;
              background: #1a365d;
              border-radius: 4px;
              display: flex;
              align-items: center;
              justify-content: center;
              color: #fff;
              font-size: 12px;
              font-weight: 600;
              flex-shrink: 0;
            }
            .pdf-section-num.gold { background: #b8860b; }
            .pdf-section-num.blue { background: #3b82f6; }
            .pdf-section-num.green { background: #10b981; }
            .pdf-section-title {
              font-size: 16px;
              font-weight: 600;
              color: #0f172a;
              letter-spacing: 1px;
            }
            .pdf-section-tag {
              margin-left: auto;
              font-size: 10px;
              padding: 3px 10px;
              background: #f1f5f9;
              color: #475569;
              border-radius: 3px;
              letter-spacing: 1px;
              text-transform: uppercase;
            }
            
            /* 内容框 */
            .pdf-box {
              background: #fafbfc;
              border: 1px solid #e5e7eb;
              border-radius: 6px;
              padding: 20px 24px;
              line-height: 1.9;
              color: #374151;
              font-size: 13.5px;
            }
            .pdf-box.fact {
              background: #fffdf7;
              border-color: #e5e0d0;
              border-left: 3px solid #b8860b;
            }
            .pdf-box.case {
              background: #f8fbff;
              border-color: #dbeafe;
              border-left: 3px solid #3b82f6;
            }
            .pdf-box.law {
              background: #f7fdf9;
              border-color: #d1fae5;
              border-left: 3px solid #10b981;
            }

            /* PDF 相似案例列表 */
            .pdf-case-list {
              display: flex;
              flex-direction: column;
              gap: 12px;
            }
            .pdf-case-item {
              border: 1px solid #dbeafe;
              background: #f8fbff;
              border-radius: 6px;
              padding: 12px 14px;
            }
            .pdf-case-title {
              font-size: 14px;
              font-weight: 650;
              color: #0f172a;
              margin-bottom: 6px;
            }
            .pdf-case-body {
              color: #475569;
              font-size: 13px;
              line-height: 1.8;
              white-space: pre-wrap;
            }
            .pdf-case-meta {
              margin-top: 8px;
              display: flex;
              flex-wrap: wrap;
              gap: 6px;
              font-size: 12px;
              color: #475569;
            }
            .pdf-case-tag {
              padding: 4px 9px;
              background: #eef2ff;
              border: 1px solid #e0e7ff;
              border-radius: 12px;
            }
            
            /* 内容排版 */
            .pdf-box h1, .pdf-box h2, .pdf-box h3, .pdf-box h4, .pdf-box h5 {
              color: #0f172a;
              margin: 20px 0 10px 0;
              font-weight: 600;
              line-height: 1.4;
            }
            .pdf-box h1 { font-size: 18px; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; }
            .pdf-box h2 { font-size: 16px; }
            .pdf-box h3 { font-size: 15px; }
            .pdf-box h4, .pdf-box h5 { font-size: 14px; }
            .pdf-box p { margin: 10px 0; }
            .pdf-box ul, .pdf-box ol { padding-left: 22px; margin: 10px 0; }
            .pdf-box li { margin: 5px 0; }
            .pdf-box strong { color: #0f172a; font-weight: 600; }
            .pdf-box hr { border: none; border-top: 1px dashed #d1d5db; margin: 18px 0; }
            .pdf-box blockquote {
              border-left: 2px solid #b8860b;
              padding-left: 14px;
              margin: 14px 0;
              color: #4b5563;
              font-style: italic;
            }
            
            /* 页脚 */
            .pdf-footer {
              margin-top: 44px;
              padding-top: 18px;
              border-top: 1px solid #e2e8f0;
              display: flex;
              justify-content: space-between;
              align-items: flex-end;
              font-size: 11px;
              color: #94a3b8;
            }
            .pdf-footer-center {
              text-align: center;
              color: #64748b;
              line-height: 1.7;
            }
          </style>
        `;

        pdfContainer.innerHTML = `
          ${pdfStyles}
          <div class="pdf-wrapper">
            <!-- 页眉 -->
            <div class="pdf-header">
              <div class="pdf-header-left">
                <div class="pdf-logo">智法</div>
                <div class="pdf-brand-name">智法AI</div>
              </div>
              <div class="pdf-header-right">
                Case Analysis Report<br>${dateStr} ${timeStr}
              </div>
            </div>
            
            <!-- 标题 -->
            <div class="pdf-title-section">
              <div class="pdf-main-title">案情分析报告</div>
              <div class="pdf-title-line"></div>
              <div class="pdf-title-sub">基于案例库检索与法律条文的智能分析</div>
            </div>
            
            <!-- 核心指标 -->
            <div class="pdf-metrics">
              <div class="pdf-metric">
                <div class="pdf-metric-label">罪名推测</div>
                <div class="pdf-metric-value" style="font-size:22px;">${
                  currentAnalysisData.predicted_accusation || currentAnalysisData.structured_prediction?.crime || "--"
                }</div>
              </div>
              <div class="pdf-metric type-b">
                <div class="pdf-metric-label">刑期区间</div>
                <div class="pdf-metric-value" style="font-size:28px;">${statsRange}</div>
                <div class="pdf-metric-unit">个月</div>
              </div>
            </div>
            
            <!-- 一、案情描述 -->
            <div class="pdf-section">
              <div class="pdf-section-head">
                <div class="pdf-section-num gold">1</div>
                <div class="pdf-section-title">案情描述</div>
                <div class="pdf-section-tag">Case Facts</div>
              </div>
              <div class="pdf-box fact">${(caseFact || "暂无案情描述")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/\n/g, "<br>")}</div>
            </div>
            
            <!-- 二、案情分析 -->
            <div class="pdf-section">
              <div class="pdf-section-head">
                <div class="pdf-section-num">2</div>
                <div class="pdf-section-title">案情分析</div>
                <div class="pdf-section-tag">Analysis</div>
              </div>
              <div class="pdf-box">${analysisHTML || "暂无分析结果"}</div>
            </div>
            
            ${
              currentAnalysisData.similar_cases_text
                ? `
            <!-- 三、相关案例 -->
            <div class="pdf-section">
              <div class="pdf-section-head">
                <div class="pdf-section-num blue">3</div>
                <div class="pdf-section-title">相关案例分析</div>
                <div class="pdf-section-tag">Similar Cases</div>
              </div>
              <div class="pdf-box case">${caseHTMLForPDF}</div>
            </div>
            `
                : ""
            }
            
            ${
              currentAnalysisData.law_context
                ? `
            <!-- 四、法律条文 -->
            <div class="pdf-section">
              <div class="pdf-section-head">
                <div class="pdf-section-num green">${
                  currentAnalysisData.similar_cases_text ? "4" : "3"
                }</div>
                <div class="pdf-section-title">相关法律条文</div>
                <div class="pdf-section-tag">Legal Reference</div>
              </div>
              <div class="pdf-box law">${lawHTML}</div>
            </div>
            `
                : ""
            }
            
            <!-- 页脚 -->
            <div class="pdf-footer">
              <div>No. ${Date.now().toString(36).toUpperCase()}</div>
              <div class="pdf-footer-center">
                本报告由智法AI智能分析系统生成，仅供参考<br>如需法律建议，请咨询专业律师
              </div>
              <div>智法AI ${now.getFullYear()}</div>
            </div>
          </div>
        `;

        document.body.appendChild(pdfContainer);

        try {
          await new Promise((r) => setTimeout(r, 150));
          const canvas = await window.html2canvas(pdfContainer, {
            scale: 2,
            useCORS: true,
            logging: false,
            backgroundColor: "#ffffff",
            windowWidth: 794,
          });

          const imgData = canvas.toDataURL("image/jpeg", 0.95);
          const { jsPDF } = window.jspdf;
          const pdf = new jsPDF("p", "mm", "a4");

          const imgWidth = 210;
          const marginTop = 12;
          const marginBottom = 12;
          const usablePageHeight = 297 - marginTop - marginBottom;
          const imgHeight = (canvas.height * imgWidth) / canvas.width;

          let heightLeft = imgHeight;
          let position = marginTop;

          pdf.addImage(imgData, "JPEG", 0, position, imgWidth, imgHeight);
          heightLeft -= usablePageHeight;

          while (heightLeft > 0) {
            position = heightLeft - imgHeight + marginTop;
            pdf.addPage();
            pdf.addImage(imgData, "JPEG", 0, position, imgWidth, imgHeight);
            heightLeft -= usablePageHeight;
          }

          const filename = `案情分析报告_${
            new Date().toISOString().split("T")[0]
          }.pdf`;
          pdf.save(filename);
        } catch (err) {
          console.error("前端PDF生成失败:", err);
          alert("PDF 生成失败: " + (err?.message || err));
        } finally {
          if (document.body.contains(pdfContainer)) {
            document.body.removeChild(pdfContainer);
          }
        }
      }

      // 数字递增动画
      function animateValue(elementId, start, end, duration) {
        const el = document.getElementById(elementId);
        if (!el || isNaN(end)) {
          el.textContent = end || "--";
          return;
        }

        const startTime = performance.now();
        const updateValue = (currentTime) => {
          const elapsed = currentTime - startTime;
          const progress = Math.min(elapsed / duration, 1);

          // 使用缓出函数
          const easeOut = 1 - Math.pow(1 - progress, 3);
          const current = Math.round(start + (end - start) * easeOut);

          el.textContent = current;

          if (progress < 1) {
            requestAnimationFrame(updateValue);
          } else {
            el.textContent = end;
          }
        };

        requestAnimationFrame(updateValue);
      }

      document.querySelectorAll(".analysis-tab").forEach((tab) => {
        tab.addEventListener("click", function () {
          document
            .querySelectorAll(".analysis-tab")
            .forEach((t) => t.classList.remove("active"));
          this.classList.add("active");
        });
      });

      // ===== 法律法规查询功能（虚拟滚动版） =====
      let lawCurrentCategory = "";
      let lawDataLoaded = false;

      async function loadLawCategories() {
        const startTime = performance.now();
        try {
          const response = await fetch("/api/laws/categories");
          const data = await response.json();

          if (data.error) {
            document.getElementById("law-categories").innerHTML =
              '<div class="loading-text">加载失败</div>';
            return;
          }

          const categories = data.categories || [];
          const loadTime = (performance.now() - startTime).toFixed(0);

          // 显示分类数量（更新左侧边栏的统计数字）
          document.getElementById("law-category-count").textContent =
            categories.length;

          // 更新分类徽章
          const categoryBadge = document.getElementById("law-category-badge");
          if (categoryBadge) {
            categoryBadge.textContent = categories.length + "类";
          }

          const totalCount = categories.reduce((sum, c) => sum + c.count, 0);

          // 更新总数显示
          const lawTotalEl = document.getElementById("law-total-count");
          if (lawTotalEl) {
            lawTotalEl.textContent = totalCount.toLocaleString("zh-CN");
          }

          // 更新右侧结果数量
          const resultCountEl = document.getElementById("law-result-count");
          if (resultCountEl) {
            resultCountEl.textContent =
              totalCount.toLocaleString("zh-CN") + " 条";
          }

          let html =
            '<div class="category-item active" onclick="selectLawCategory(\'\')" data-category="">' +
            '<span class="category-name">全部法律</span>' +
            '<span class="category-badge">' +
            totalCount.toLocaleString("zh-CN") +
            "</span></div>";

          for (const cat of categories) {
            html += `<div class="category-item" onclick="selectLawCategory('${
              cat.name
            }')" data-category="${cat.name}">
                    <span class="category-name">${cat.name}</span>
                    <span class="category-badge">${cat.count.toLocaleString(
                      "zh-CN"
                    )}</span>
                </div>`;
          }

          document.getElementById("law-categories").innerHTML = html;

          // 输出性能日志（仅控制台）
          const cacheStatus = data.cached ? " (已缓存)" : "";
          console.log(`[性能] 法律分类加载完成: ${loadTime}ms${cacheStatus}`);

          // 自动加载全部法律数据
          loadAllLawData();
        } catch (err) {
          document.getElementById("law-categories").innerHTML =
            '<div class="loading-text">加载失败: ' + err.message + "</div>";
        }
      }

      // 加载全部法律数据（用于虚拟滚动）
      async function loadAllLawData() {
        if (lawDataLoaded) return;

        try {
          await lawDataManager.loadAllLaws();
          lawDataLoaded = true;
        } catch (err) {
          console.error("加载法律数据失败:", err);
          document.getElementById("law-content").innerHTML =
            '<div class="empty-hint">数据加载失败，请刷新页面重试</div>';
        }
      }

      async function selectLawCategory(category) {
        lawCurrentCategory = category;

        document
          .querySelectorAll("#law-categories .category-item")
          .forEach((item) => {
            item.classList.remove("active");
            if (item.dataset.category === category) {
              item.classList.add("active");
            }
          });

        // 更新右侧标题
        const titleEl = document.getElementById("laws-current-category-title");
        if (titleEl) {
          titleEl.textContent = category || "全部法律";
        }

        updateLawFilterTags();

        // 使用虚拟滚动的过滤功能
        if (lawDataManager.virtualScroll) {
          const startTime = performance.now();
          const count = lawDataManager.filterByCategory(category);
          const filterTime = performance.now() - startTime;

          // 更新结果数量徽章
          const resultCountEl = document.getElementById("law-result-count");
          if (resultCountEl) {
            resultCountEl.textContent = count.toLocaleString("zh-CN") + " 条";
          }

          // 同时应用搜索过滤
          const query = document
            .getElementById("law-search-input")
            .value.trim();
          if (query) {
            lawDataManager.search(query);
          } else {
            lawDataManager.updateStats(filterTime, count, true);
          }
        } else {
          // 数据还未加载，先加载
          await loadAllLawData();
          if (category) {
            lawDataManager.filterByCategory(category);
          }
        }
      }

      function updateLawFilterTags() {
        let html = "";
        if (lawCurrentCategory) {
          html += `<span class="laws-filter-tag">
                <span>${lawCurrentCategory}</span>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" onclick="removeLawCategoryFilter()">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </span>`;
        }
        const filterTagsEl = document.getElementById("law-filter-tags");
        if (filterTagsEl) {
          filterTagsEl.innerHTML = html;
        }
      }

      function removeLawCategoryFilter() {
        selectLawCategory("");
      }

      // 当前搜索关键词（用于高亮）
      let lawCurrentQuery = "";

      // 快速前端搜索函数
      function searchLaws() {
        const query = document.getElementById("law-search-input").value.trim();
        lawCurrentQuery = query;

        // 保存搜索历史
        if (query) {
          lawSearchHistory.addItem(query);
        }

        // 使用虚拟滚动的搜索功能（毫秒级响应）
        if (lawDataManager.virtualScroll) {
          lawDataManager.search(query);
        } else {
          // 数据还未加载
          document.getElementById("law-result-count").innerHTML =
            '<span class="search-status">数据加载中...</span>';
        }
      }

      // 创建防抖版本的法律搜索函数
      const debouncedSearchLaws = debounce(() => {
        searchLaws();
      }, 150); // 缩短防抖时间，因为前端搜索很快

      // 监听法律搜索框事件
      const lawSearchInput = document.getElementById("law-search-input");

      // 回车搜索
      lawSearchInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          searchLaws();
          hideLawSearchHistory();
        } else if (e.key === "Escape") {
          hideLawSearchHistory();
        }
      });

      // 实时搜索（带防抖）- 毫秒级响应
      lawSearchInput.addEventListener("input", function (e) {
        debouncedSearchLaws();
      });

      // 显示搜索历史
      lawSearchInput.addEventListener("focus", function () {
        showLawSearchHistory();
      });

      // 点击外部关闭搜索历史
      document.addEventListener("click", function (e) {
        const wrapper = document.querySelector("#panel-laws .laws-search-box");
        if (wrapper && !wrapper.contains(e.target)) {
          hideLawSearchHistory();
        }
      });

      // 搜索历史显示/隐藏函数
      function showLawSearchHistory() {
        const history = lawSearchHistory.getHistory();
        if (history.length === 0) return;

        let dropdown = document.getElementById("law-search-history");
        if (!dropdown) {
          dropdown = document.createElement("div");
          dropdown.id = "law-search-history";
          dropdown.className = "search-history-dropdown";
          const wrapper = lawSearchInput.parentElement;
          wrapper.appendChild(dropdown);
        }

        let html = `<div class="search-history-header">
            <span>搜索历史</span>
            <button class="search-history-clear" onclick="clearLawSearchHistory()">清除</button>
        </div>`;

        for (const item of history) {
          html += `<div class="search-history-item" onclick="selectLawHistory('${item.replace(
            /'/g,
            "\\'"
          )}')">
                <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                <span>${escapeHtml(item)}</span>
            </div>`;
        }

        dropdown.innerHTML = html;
        dropdown.classList.add("show");
      }

      function hideLawSearchHistory() {
        const dropdown = document.getElementById("law-search-history");
        if (dropdown) {
          dropdown.classList.remove("show");
        }
      }

      function selectLawHistory(query) {
        lawSearchInput.value = query;
        searchLaws();
        hideLawSearchHistory();
      }

      function clearLawSearchHistory() {
        lawSearchHistory.clearHistory();
        hideLawSearchHistory();
      }

      // 清除法律搜索
      function clearLawSearch() {
        document.getElementById("law-search-input").value = "";
        document.getElementById("law-search-clear").style.display = "none";
        searchLaws();
      }

      // 监听法律搜索输入
      const lawSearchInputNew = document.getElementById("law-search-input");
      if (lawSearchInputNew) {
        lawSearchInputNew.addEventListener("input", function () {
          const clearBtn = document.getElementById("law-search-clear");
          if (clearBtn) {
            if (this.value) {
              clearBtn.style.display = "flex";
            } else {
              clearBtn.style.display = "none";
            }
          }
        });
      }

      // ===== 案例库查询功能（虚拟滚动优化版）=====
      let caseCurrentAccusation = "";
      let caseImprisonmentMin = null;
      let caseImprisonmentMax = null;

      let allAccusations = []; // 存储所有罪名数据

      // 案例数据管理器（分批渐进式加载版）
      class CaseDataManager {
        constructor() {
          this.allCases = [];
          this.isLoading = false;
          this.isLoaded = false;
          this.loadingBatch = false;
          this.currentBatch = 0;
          this.batchSize = 30000;
          this.totalCases = 150327;
          this.virtualScroll = null;
          this.currentQuery = "";
          this.currentAccusation = "";
          this.imprisonmentMin = null;
          this.imprisonmentMax = null;
          this.startTime = 0;
        }

        async loadAllCases() {
          if (this.isLoading) return;
          if (this.isLoaded) {
            // 如果已加载完成，直接执行搜索
            return;
          }

          this.isLoading = true;
          this.startTime = performance.now();
          this.currentBatch = 0;
          this.allCases = [];

          // 显示加载进度
          this.updateProgress(0, this.totalCases, "正在加载案例库...");

          try {
            // 渐进式加载所有批次
            await this.loadNextBatch();
          } catch (err) {
            console.error("加载案例数据失败:", err);
            const content = document.getElementById("case-content");
            if (content) {
              content.innerHTML = `<div class="empty-hint">${I18n.t(
                "notifications.loadingFailed"
              )}: ${err.message}</div>`;
            }
            this.updateProgress(
              0,
              0,
              I18n.t("notifications.loadingFailed"),
              true
            );
            this.isLoading = false;
            throw err;
          }
        }

        async loadNextBatch() {
          if (this.loadingBatch) return;
          this.loadingBatch = true;

          try {
            const response = await fetch(
              `/api/cases/all?batch=${this.currentBatch}&batch_size=${this.batchSize}`
            );
            const data = await response.json();

            if (data.error) {
              throw new Error(data.error);
            }

            const newCases = data.cases || [];
            this.allCases = this.allCases.concat(newCases);
            this.totalCases = data.total;

            const loadedCount = this.allCases.length;
            const loadTime = (performance.now() - this.startTime).toFixed(0);
            const progress = Math.round((loadedCount / this.totalCases) * 100);

            console.log(
              `[批次加载] 批次${this.currentBatch}: 加载 ${newCases.length} 条, 总计 ${loadedCount}/${this.totalCases} (${progress}%), 耗时 ${loadTime}ms`
            );

            // 更新进度条
            this.updateProgress(
              loadedCount,
              this.totalCases,
              `正在加载案例库... ${progress}%`
            );

            // 第一批加载完成后立即初始化虚拟滚动（让用户能先看到数据）
            if (this.currentBatch === 0) {
              this.initVirtualScroll();
            } else {
              // 后续批次更新虚拟滚动数据
              if (this.virtualScroll) {
                this.virtualScroll.setItems(this.allCases);
              }
            }

            // 更新结果计数
            const statusText = data.has_more
              ? `已加载 ${loadedCount.toLocaleString()} / ${this.totalCases.toLocaleString()} 条案例 · <span class="search-time">${loadTime}ms</span> <span class="loading-badge">加载中...</span>`
              : `共 ${loadedCount.toLocaleString()} 条案例 · <span class="search-time">${loadTime}ms</span> <span class="cache-hit">全部加载</span>`;
            document.getElementById(
              "case-result-count"
            ).innerHTML = `<span class="search-status">${statusText}</span>`;

            this.loadingBatch = false;

            // 如果还有更多数据，继续加载下一批
            if (data.has_more) {
              this.currentBatch++;
              // 使用setTimeout让UI有时间更新
              setTimeout(() => this.loadNextBatch(), 100);
            } else {
              // 全部加载完成
              this.isLoaded = true;
              this.isLoading = false;
              this.hideProgress();

              const totalTime = (performance.now() - this.startTime).toFixed(0);
              console.log(
                `[加载完成] 全部 ${this.allCases.length} 条案例加载完成，总耗时 ${totalTime}ms`
              );

              // 执行当前搜索
              this.search(this.currentQuery);
            }
          } catch (err) {
            this.loadingBatch = false;
            throw err;
          }
        }

        updateProgress(loaded, total, text, isError = false) {
          const progressEl = document.getElementById("case-load-progress");
          if (!progressEl) return;

          progressEl.style.display = "flex";
          const textEl = progressEl.querySelector(".progress-text");
          const fillEl = progressEl.querySelector(".progress-fill");

          if (textEl) textEl.textContent = text;
          if (fillEl) {
            const percent = total > 0 ? (loaded / total) * 100 : 0;
            fillEl.style.width = `${percent}%`;
            fillEl.style.background = isError
              ? "#ef4444"
              : "linear-gradient(90deg, #3b82f6, #10b981)";
          }
        }

        hideProgress() {
          const progressEl = document.getElementById("case-load-progress");
          if (progressEl) {
            progressEl.style.display = "none";
          }
        }

        initVirtualScroll() {
          const container = document.getElementById("case-virtual-container");
          const viewport = document.getElementById("case-results");
          const content = document.getElementById("case-content");
          const spacer = document.getElementById("case-spacer");
          const scrollInfo = document.getElementById("case-scroll-info");

          if (!container || !viewport || !content || !spacer) {
            console.error("案例虚拟滚动容器未找到");
            return;
          }

          // 创建虚拟滚动实例
          this.virtualScroll = new VirtualScroll({
            container,
            viewport,
            content,
            spacer,
            itemHeight: 140,
            bufferSize: 10,
            columns: 2,
            renderItem: this.renderCaseItem.bind(this),
            onScroll: (info) => {
              // 更新滚动位置信息
              const posEl = scrollInfo.querySelector(".scroll-position");
              if (posEl && info.total > 0) {
                posEl.textContent = `显示 ${info.startIndex + 1} - ${Math.min(
                  info.endIndex,
                  info.total
                )} / ${info.total} 条`;
              }
            },
          });

          // 设置数据
          this.virtualScroll.setItems(this.allCases);

          // 绑定回到顶部按钮
          const scrollToTopBtn = scrollInfo.querySelector(".scroll-to-top");
          if (scrollToTopBtn) {
            scrollToTopBtn.onclick = () => this.virtualScroll.scrollToTop();
          }
        }

        renderCaseItem(item, index) {
          const query = this.currentQuery;

          // 转义HTML特殊字符
          const escapeHtml = (str) => {
            return String(str || "")
              .replace(/&/g, "&amp;")
              .replace(/</g, "&lt;")
              .replace(/>/g, "&gt;")
              .replace(/"/g, "&quot;")
              .replace(/'/g, "&#39;");
          };

          let fact = escapeHtml(item.fact || "");
          let accusation = escapeHtml(item.accusation || "未知罪名");

          // 高亮搜索关键词
          if (query) {
            const terms = query.split(/\s+/).filter((t) => t);
            terms.forEach((term) => {
              const escapedTerm = escapeHtml(term);
              const regex = new RegExp(
                `(${escapedTerm.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`,
                "gi"
              );
              fact = fact.replace(regex, "<mark>$1</mark>");
              accusation = accusation.replace(regex, "<mark>$1</mark>");
            });
          }

          // 获取刑罚文本
          let punishment = "";
          if (item.death_penalty) {
            punishment = "死刑";
          } else if (item.life_imprisonment) {
            punishment = "无期徒刑";
          } else {
            const months = item.imprisonment || 0;
            if (months >= 12) {
              const years = Math.floor(months / 12);
              const remainMonths = months % 12;
              punishment =
                remainMonths > 0
                  ? `${years}年${remainMonths}个月`
                  : `${years}年`;
            } else {
              punishment = months + "个月";
            }
          }

          const moneyHtml =
            item.punish_of_money > 0
              ? `<span class="punishment-tag">罚金 ${item.punish_of_money.toLocaleString()} 元</span>`
              : "";

          // 使用item.id作为真实ID，确保API调用正确
          const itemId = item.id !== undefined ? item.id : index;

          return `<div class="case-card clickable" data-id="${itemId}" onclick="openCaseDetail(${itemId})">
                <div class="case-body">
                    <div class="case-fact">${fact}</div>
                </div>
                <div class="case-meta">
                    <div class="case-meta-right">
                        <div class="case-meta-tags">
                            <span class="case-meta-chip accent">${accusation}</span>
                            <span class="case-meta-separator">·</span>
                            <span class="case-meta-chip strong">${punishment}</span>
                            ${
                              moneyHtml
                                ? `<span class="case-meta-separator">·</span>` +
                                  moneyHtml.replace(
                                    "punishment-tag",
                                    "case-meta-chip"
                                  )
                                : ""
                            }
                        </div>
                        <span class="click-hint">
                            详情
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M5 12h14"></path>
                                <path d="M12 5l7 7-7 7"></path>
                            </svg>
                        </span>
                    </div>
                </div>
            </div>`;
        }

        search(query) {
          this.currentQuery = query;

          if (!this.virtualScroll) {
            console.warn("案例虚拟滚动未初始化");
            return 0;
          }

          const startTime = performance.now();

          // 构建过滤函数
          const filterFn = (item) => {
            // 关键词搜索
            if (query) {
              const searchTerms = query
                .toLowerCase()
                .split(/\s+/)
                .filter((t) => t);
              const searchText = `${item.fact || ""} ${
                item.accusation || ""
              }`.toLowerCase();
              if (!searchTerms.every((term) => searchText.includes(term))) {
                return false;
              }
            }

            // 罪名筛选
            if (this.currentAccusation) {
              if (!(item.accusation || "").includes(this.currentAccusation)) {
                return false;
              }
            }

            // 刑期筛选
            if (
              this.imprisonmentMin !== null ||
              this.imprisonmentMax !== null
            ) {
              const imprisonment = item.imprisonment || 0;
              const isDeathPenalty = item.death_penalty;
              const isLifeImprisonment = item.life_imprisonment;

              // 特殊处理死刑和无期
              if (this.imprisonmentMin === -2 && this.imprisonmentMax === -2) {
                if (!isDeathPenalty) return false;
              } else if (
                this.imprisonmentMin === -1 &&
                this.imprisonmentMax === -1
              ) {
                if (!isLifeImprisonment) return false;
              } else {
                if (isDeathPenalty || isLifeImprisonment) return false;
                if (
                  this.imprisonmentMin !== null &&
                  imprisonment < this.imprisonmentMin
                )
                  return false;
                if (
                  this.imprisonmentMax !== null &&
                  imprisonment >= this.imprisonmentMax
                )
                  return false;
              }
            }

            return true;
          };

          const resultCount = this.virtualScroll.filterItems(filterFn);
          const searchTime = (performance.now() - startTime).toFixed(0);

          // 更新结果计数
          const loadedInfo = this.isLoaded
            ? ""
            : ` (已加载 ${this.allCases.length.toLocaleString()}/${this.totalCases.toLocaleString()})`;
          const cacheHtml = '<span class="cache-hit">本地</span>';
          document.getElementById(
            "case-result-count"
          ).innerHTML = `<span class="search-status">共 ${resultCount.toLocaleString()} 条案例${loadedInfo}
                <span class="status-icon"><svg viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg></span>
                <span class="search-time">${searchTime}ms</span>
                ${cacheHtml}</span>`;

          console.log(
            `[前端搜索] 案例搜索完成: ${searchTime}ms, 结果 ${resultCount} 条`
          );

          return resultCount;
        }

        setFilters(accusation, imprisonmentMin, imprisonmentMax) {
          this.currentAccusation = accusation || "";
          this.imprisonmentMin = imprisonmentMin;
          this.imprisonmentMax = imprisonmentMax;
        }
      }

      // 创建案例数据管理器实例
      const caseDataManager = new CaseDataManager();
      window.caseDataManager = caseDataManager;

      async function loadAccusations() {
        const startTime = performance.now();
        try {
          const response = await fetch("/api/cases/accusations");
          const data = await response.json();

          if (data.error) {
            document.getElementById("accusation-list").innerHTML =
              '<div class="loading-text">加载失败</div>';
            return;
          }

          allAccusations = data.accusations || [];
          const loadTime = (performance.now() - startTime).toFixed(0);

          // 更新左侧边栏的统计数字
          const accusationCountEl = document.getElementById("accusation-count");
          if (accusationCountEl) {
            accusationCountEl.textContent = allAccusations.length;
          }

          renderAccusationList(allAccusations);

          // 输出性能日志（仅控制台）
          const cacheStatus = data.cached ? " (已缓存)" : "";
          console.log(`[性能] 罪名列表加载完成: ${loadTime}ms${cacheStatus}`);
        } catch (err) {
          document.getElementById("accusation-list").innerHTML =
            '<div class="loading-text">加载失败</div>';
        }
      }

      function renderAccusationList(accusations) {
        // 只显示前50个常见罪名
        const displayAccusations = accusations.slice(0, 50);

        // 新版HTML结构 - 使用 filter-option-item 类
        let html = `<div class="filter-option-item" onclick="selectAccusationNew('', '全部罪名')" data-accusation="">
                        <span class="option-name">全部罪名</span>
                        <span class="option-count">${allAccusations
                          .reduce((sum, a) => sum + a.count, 0)
                          .toLocaleString()}</span>
                    </div>`;

        for (const acc of displayAccusations) {
          const escapedName = acc.name.replace(/'/g, "\\'");
          html += `<div class="filter-option-item" onclick="selectAccusationNew('${escapedName}', '${escapedName}')" data-accusation="${
            acc.name
          }">
                <span class="option-name">${acc.name}</span>
                <span class="option-count">${acc.count.toLocaleString()}</span>
            </div>`;
        }

        document.getElementById("accusation-list").innerHTML = html;
      }

      // 罪名搜索功能
      document
        .getElementById("accusation-search")
        ?.addEventListener("input", function (e) {
          const keyword = e.target.value.trim().toLowerCase();
          if (!keyword) {
            renderAccusationList(allAccusations);
            return;
          }
          const filtered = allAccusations.filter((acc) =>
            acc.name.toLowerCase().includes(keyword)
          );
          renderAccusationList(filtered);
        });

      // 动态定位弹出框
      function positionDropdown(card, dropdown) {
        const cardRect = card.getBoundingClientRect();
        const dropdownWidth = 360;
        const dropdownHeight = Math.min(480, window.innerHeight - 40);

        // 计算弹出框位置（显示在卡片右侧）
        let left = cardRect.right + 16;
        let top = cardRect.top;

        // 如果右侧空间不够，显示在左侧
        if (left + dropdownWidth > window.innerWidth - 20) {
          left = cardRect.left - dropdownWidth - 16;
        }

        // 确保不超出屏幕底部
        if (top + dropdownHeight > window.innerHeight - 20) {
          top = window.innerHeight - dropdownHeight - 20;
        }

        // 确保不超出屏幕顶部
        if (top < 20) {
          top = 20;
        }

        dropdown.style.left = left + "px";
        dropdown.style.top = top + "px";
      }

      // 为筛选卡片添加定位事件
      const accusationCard = document.getElementById("accusation-card");
      const accusationDropdown = document.getElementById("accusation-dropdown");
      const imprisonmentCard = document.getElementById("imprisonment-card");
      const imprisonmentDropdown = document.getElementById(
        "imprisonment-dropdown"
      );

      if (accusationCard && accusationDropdown) {
        accusationCard.addEventListener("mouseenter", () => {
          positionDropdown(accusationCard, accusationDropdown);
        });
      }

      if (imprisonmentCard && imprisonmentDropdown) {
        imprisonmentCard.addEventListener("mouseenter", () => {
          positionDropdown(imprisonmentCard, imprisonmentDropdown);
        });
      }

      async function loadCaseStats() {
        try {
          const response = await fetch("/api/cases/stats");
          const data = await response.json();

          if (data.error) return;

          // 更新总案例数
          const totalCases = data.total_cases || 0;
          const totalCountEl = document.getElementById("total-cases-count");
          if (totalCountEl) {
            totalCountEl.textContent = totalCases.toLocaleString();
          }

          const ranges = data.imprisonment_ranges || [];
          for (const r of ranges) {
            const id = `imp-${r.min}-${r.max}`;
            const el = document.getElementById(id);
            if (el) el.textContent = r.count.toLocaleString();
          }
        } catch (err) {
          console.error("加载案例统计失败:", err);
        }
      }

      function selectAccusation(accusation) {
        caseCurrentAccusation = accusation;
        caseCurrentPage = 1;

        document
          .querySelectorAll("#accusation-list .filter-dropdown-item")
          .forEach((item) => {
            item.classList.remove("active");
            if (item.dataset.accusation === accusation) {
              item.classList.add("active");
            }
          });

        updateCurrentFilters();
        updateCaseFilterTags();
        searchCases();

        // 选择后关闭下拉框
        document.getElementById("accusation-card").classList.remove("expanded");
      }

      // ===== 案例库新筛选交互 =====

      // 切换筛选下拉框
      function toggleCaseFilter(filterType) {
        const wrapper = document.getElementById(filterType + "-wrapper");
        const isOpen = wrapper.classList.contains("open");

        // 关闭所有其他下拉框
        document
          .querySelectorAll(".filter-select-wrapper.open")
          .forEach((w) => {
            if (w !== wrapper) {
              w.classList.remove("open");
            }
          });

        // 切换当前下拉框
        if (isOpen) {
          wrapper.classList.remove("open");
        } else {
          wrapper.classList.add("open");
        }
      }

      // 点击外部区域关闭下拉框
      document.addEventListener("click", function (e) {
        if (!e.target.closest(".filter-select-wrapper")) {
          document
            .querySelectorAll(".filter-select-wrapper.open")
            .forEach((w) => {
              w.classList.remove("open");
            });
        }
      });

      // 选择刑期（新版）
      function selectImprisonmentNew(el) {
        const min = parseInt(el.dataset.min);
        const max = parseInt(el.dataset.max);

        // 取消之前选中的项
        document
          .querySelectorAll("#imprisonment-list .filter-option-item")
          .forEach((item) => {
            item.classList.remove("active");
          });

        // 切换选中状态
        if (caseImprisonmentMin === min && caseImprisonmentMax === max) {
          caseImprisonmentMin = null;
          caseImprisonmentMax = null;
        } else {
          el.classList.add("active");
          caseImprisonmentMin = min;
          caseImprisonmentMax = max;
        }

        // 更新显示
        updateCaseFiltersDisplay();
        searchCases();
      }

      // 选择罪名（新版）
      function selectAccusationNew(accusation, displayName) {
        // 取消之前选中的项
        document
          .querySelectorAll("#accusation-list .filter-option-item")
          .forEach((item) => {
            item.classList.remove("active");
          });

        if (caseCurrentAccusation === accusation) {
          caseCurrentAccusation = "";
        } else {
          caseCurrentAccusation = accusation;
          // 标记选中项
          document
            .querySelectorAll("#accusation-list .filter-option-item")
            .forEach((item) => {
              if (item.dataset.accusation === accusation) {
                item.classList.add("active");
              }
            });
        }

        // 更新显示
        updateCaseFiltersDisplay();
        searchCases();
      }

      // 更新筛选条件显示
      function updateCaseFiltersDisplay() {
        const container = document.getElementById("current-case-filters");
        let html = "";

        // 更新右侧标题
        const titleEl = document.getElementById("cases-current-filter-title");
        if (titleEl) {
          if (caseCurrentAccusation) {
            titleEl.textContent = caseCurrentAccusation;
          } else if (caseImprisonmentMin !== null) {
            titleEl.textContent = getImprisonmentRangeText(
              caseImprisonmentMin,
              caseImprisonmentMax
            );
          } else {
            titleEl.textContent = I18n.t("cases.allTypes");
          }
        }

        if (caseCurrentAccusation) {
          html += `<span class="cases-filter-tag">
                <span>罪名: ${caseCurrentAccusation}</span>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" onclick="clearAccusationFilter()">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </span>`;
        }

        if (caseImprisonmentMin !== null) {
          const rangeText = getImprisonmentRangeText(
            caseImprisonmentMin,
            caseImprisonmentMax
          );
          html += `<span class="cases-filter-tag">
                <span>刑期: ${rangeText}</span>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" onclick="clearImprisonmentFilter()">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </span>`;
        }

        if (container) {
          container.innerHTML = html;
        }
      }

      // 清除罪名筛选
      function clearAccusationFilter() {
        caseCurrentAccusation = "";
        document
          .querySelectorAll("#accusation-list .filter-option-item")
          .forEach((item) => {
            item.classList.remove("active");
          });
        updateCaseFiltersDisplay();
        searchCases();
      }

      // 清除刑期筛选
      function clearImprisonmentFilter() {
        caseImprisonmentMin = null;
        caseImprisonmentMax = null;
        document
          .querySelectorAll("#imprisonment-list .filter-option-item")
          .forEach((item) => {
            item.classList.remove("active");
          });
        updateCaseFiltersDisplay();
        searchCases();
      }

      // 清除所有筛选
      function clearAllCaseFilters() {
        clearAccusationFilter();
        clearImprisonmentFilter();
        clearCaseSearch();
      }

      // 清除搜索
      function clearCaseSearch() {
        document.getElementById("case-search-input").value = "";
        document.getElementById("case-search-clear").style.display = "none";
        searchCases();
      }

      // 监听搜索输入
      const caseSearchInputNew = document.getElementById("case-search-input");
      if (caseSearchInputNew) {
        caseSearchInputNew.addEventListener("input", function () {
          const clearBtn = document.getElementById("case-search-clear");
          if (this.value) {
            clearBtn.style.display = "flex";
          } else {
            clearBtn.style.display = "none";
          }
        });

        caseSearchInputNew.addEventListener("keydown", function (e) {
          if (e.key === "Enter") {
            searchCases();
          }
        });
      }

      // 筛选罪名列表
      function filterAccusationList() {
        const searchText = document
          .getElementById("accusation-search")
          .value.toLowerCase();
        const items = document.querySelectorAll(
          "#accusation-list .filter-select-item"
        );

        items.forEach((item) => {
          const name = item
            .querySelector(".item-name")
            .textContent.toLowerCase();
          if (name.includes(searchText)) {
            item.style.display = "flex";
          } else {
            item.style.display = "none";
          }
        });
      }

      // 旧版兼容函数
      function toggleFilterDropdown(filterItem, event) {
        // 兼容旧版代码
      }

      function selectImprisonment(el) {
        const min = parseInt(el.dataset.min);
        const max = parseInt(el.dataset.max);

        // 切换选中状态
        if (el.classList.contains("active")) {
          el.classList.remove("active");
          caseImprisonmentMin = null;
          caseImprisonmentMax = null;
        } else {
          document
            .querySelectorAll("#imprisonment-list .filter-dropdown-item")
            .forEach((item) => {
              item.classList.remove("active");
            });
          el.classList.add("active");
          caseImprisonmentMin = min;
          caseImprisonmentMax = max;
        }

        caseCurrentPage = 1;
        updateCurrentFilters();
        updateCaseFilterTags();
        searchCases();

        // 选择后关闭下拉框
        el.closest(".filter-item").classList.remove("expanded");
      }

      function updateCaseFilterTags() {
        let html = "";
        if (caseCurrentAccusation) {
          html += `<span class="filter-tag">${caseCurrentAccusation} <span class="remove-tag" onclick="clearAccusationFilter()">×</span></span>`;
        }
        if (caseImprisonmentMin !== null) {
          const rangeText = getImprisonmentRangeText(
            caseImprisonmentMin,
            caseImprisonmentMax
          );
          html += `<span class="filter-tag">${rangeText} <span class="remove-tag" onclick="clearImprisonmentFilter()">×</span></span>`;
        }
        document.getElementById("case-filter-tags").innerHTML = html;
      }

      function getImprisonmentRangeText(min, max) {
        if (min === 0 && max === 6) return "6个月以下";
        if (min === 6 && max === 12) return "6个月-1年";
        if (min === 12 && max === 36) return "1-3年";
        if (min === 36 && max === 60) return "3-5年";
        if (min === 60 && max === 120) return "5-10年";
        if (min === 120) return "10年以上";
        return "刑期筛选";
      }

      // 更新当前筛选标签显示
      function updateCurrentFilters() {
        const container = document.getElementById("current-case-filters");
        if (!container) return;

        let html = "";

        if (caseCurrentAccusation) {
          html += `<div class="current-filter-tag">
                <span>罪名: ${caseCurrentAccusation}</span>
                <span class="remove-filter" onclick="removeAccusationFilter()">×</span>
            </div>`;
        }

        if (caseImprisonmentMin !== null) {
          const rangeText = getImprisonmentRangeText(
            caseImprisonmentMin,
            caseImprisonmentMax
          );
          html += `<div class="current-filter-tag">
                <span>刑期: ${rangeText}</span>
                <span class="remove-filter" onclick="removeImprisonmentFilter()">×</span>
            </div>`;
        }

        container.innerHTML = html;
      }

      function getImprisonmentRangeText(min, max) {
        if (min === 0 && max === 6) return "6个月以下";
        if (min === 6 && max === 12) return "6个月-1年";
        if (min === 12 && max === 36) return "1-3年";
        if (min === 36 && max === 60) return "3-5年";
        if (min === 60 && max === 120) return "5-10年";
        if (min === 120 && max === 999) return "10年以上";
        return "";
      }

      function removeAccusationFilter() {
        caseCurrentAccusation = "";
        document
          .querySelectorAll("#accusation-list .filter-dropdown-item")
          .forEach((item) => {
            item.classList.remove("active");
          });
        updateCurrentFilters();
        updateCaseFilterTags();
        searchCases();
      }

      function removeImprisonmentFilter() {
        caseImprisonmentMin = null;
        caseImprisonmentMax = null;
        document
          .querySelectorAll("#imprisonment-list .filter-dropdown-item")
          .forEach((item) => {
            item.classList.remove("active");
          });
        updateCurrentFilters();
        updateCaseFilterTags();
        searchCases();
      }

      // 加载全部案例数据（用于虚拟滚动，和法律法规库一样自动加载）
      async function loadAllCaseData() {
        if (caseDataManager.isLoaded) return;

        try {
          await caseDataManager.loadAllCases();
        } catch (err) {
          console.error("加载案例数据失败:", err);
          document.getElementById("case-content").innerHTML =
            '<div class="empty-hint">数据加载失败，请刷新页面重试</div>';
        }
      }

      // 案例搜索函数（虚拟滚动版）
      async function searchCases() {
        const query = document.getElementById("case-search-input").value.trim();

        // 更新筛选条件
        caseDataManager.setFilters(
          caseCurrentAccusation,
          caseImprisonmentMin,
          caseImprisonmentMax
        );

        // 如果数据未加载，先加载数据
        if (!caseDataManager.isLoaded) {
          await caseDataManager.loadAllCases();
        }

        // 保存搜索历史
        if (query) {
          caseSearchHistory.addItem(query);
        }

        // 执行搜索
        caseDataManager.search(query);
      }

      // 创建防抖版本的案例搜索函数
      const debouncedSearchCases = debounce(() => {
        searchCases();
      }, 300);

      // 监听案例搜索框事件
      const caseSearchInput = document.getElementById("case-search-input");

      // 回车搜索
      caseSearchInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          caseCurrentPage = 1;
          searchCases();
          hideCaseSearchHistory();
        } else if (e.key === "Escape") {
          hideCaseSearchHistory();
        }
      });

      // 实时搜索（带防抖）
      caseSearchInput.addEventListener("input", function (e) {
        debouncedSearchCases();
      });

      // 显示搜索历史
      caseSearchInput.addEventListener("focus", function () {
        showCaseSearchHistory();
      });

      // 点击外部关闭搜索历史
      document.addEventListener("click", function (e) {
        const wrapper = document.querySelector(
          "#panel-cases .search-input-wrapper"
        );
        if (wrapper && !wrapper.contains(e.target)) {
          hideCaseSearchHistory();
        }
      });

      // 案例搜索历史显示/隐藏函数
      function showCaseSearchHistory() {
        const history = caseSearchHistory.getHistory();
        if (history.length === 0) return;

        let dropdown = document.getElementById("case-search-history");
        if (!dropdown) {
          dropdown = document.createElement("div");
          dropdown.id = "case-search-history";
          dropdown.className = "search-history-dropdown";
          const wrapper = caseSearchInput.parentElement;
          wrapper.appendChild(dropdown);
        }

        let html = `<div class="search-history-header">
            <span>搜索历史</span>
            <button class="search-history-clear" onclick="clearCaseSearchHistory()">清除</button>
        </div>`;

        for (const item of history) {
          html += `<div class="search-history-item" onclick="selectCaseHistory('${item.replace(
            /'/g,
            "\\'"
          )}')">
                <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                <span>${escapeHtml(item)}</span>
            </div>`;
        }

        dropdown.innerHTML = html;
        dropdown.classList.add("show");
      }

      function hideCaseSearchHistory() {
        const dropdown = document.getElementById("case-search-history");
        if (dropdown) {
          dropdown.classList.remove("show");
        }
      }

      function selectCaseHistory(query) {
        caseSearchInput.value = query;
        caseCurrentPage = 1;
        searchCases();
        hideCaseSearchHistory();
      }

      function clearCaseSearchHistory() {
        caseSearchHistory.clearHistory();
        hideCaseSearchHistory();
      }

      function escapeHtml(text) {
        if (!text) return "";
        return text
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#039;");
      }

      // ===== 初始化加载 =====
      // 当切换到各面板时加载数据
      const originalSwitchPanel = switchPanel;
      window.switchPanel = function (panelId) {
        if (typeof originalSwitchPanel === "function") {
          originalSwitchPanel(panelId);
        }

        if (panelId === "laws") {
          const lawCats = document.getElementById("law-categories");
          if (lawCats && lawCats.innerHTML.includes("加载中")) {
            loadLawCategories();
          }
        } else if (panelId === "cases") {
          const accList = document.getElementById("accusation-list");
          if (accList && accList.innerHTML.includes("加载中")) {
            loadAccusations();
            loadCaseStats();
          }
          // 自动加载所有案例数据（和法律法规库一样）
          if (window.caseDataManager && !caseDataManager.isLoaded) {
            loadAllCaseData();
          }
        } else if (panelId === "settings") {
          initSettingsPanel();
        }
      };

      console.log("Script loaded successfully");
