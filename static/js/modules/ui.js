/**
 * UI交互模块
 * 负责消息提示、加载动画等UI交互
 */

Object.assign(VideoTranscriber.prototype, {
    // 消息显示
    showError(message) {
        this.hideMessages();
        this.errorMessage.textContent = message;
        this.errorMessage.style.display = 'block';
        this.errorMessage.scrollIntoView({ behavior: 'smooth', block: 'center' });
        
        // 5秒后自动隐藏
        setTimeout(() => {
            this.errorMessage.style.display = 'none';
        }, 5000);
    },

    showSuccess(message) {
        this.hideMessages();
        this.successMessage.textContent = message;
        this.successMessage.style.display = 'block';
        
        // 3秒后自动隐藏
        setTimeout(() => {
            this.successMessage.style.display = 'none';
        }, 3000);
    },

    hideMessages() {
        this.errorMessage.style.display = 'none';
        this.successMessage.style.display = 'none';
    },

    showLoading(title, message) {
        // 隐藏暂无视频占位
        const emptyState = document.getElementById('emptyState');
        if (emptyState) {
            emptyState.style.display = 'none';
        }
        
        // 隐藏其他区域
        if (this.videoPreview) this.videoPreview.style.display = 'none';
        if (this.progressSection) this.progressSection.style.display = 'none';
        if (this.downloadSection) this.downloadSection.style.display = 'none';
        if (this.resultsSection) this.resultsSection.style.display = 'none';
        
        // 显示加载动画
        if (this.loadingContainer) {
            this.loadingContainer.classList.add('show');
            
            // 更新加载文本
            const loadingText = this.loadingContainer.querySelector('.loading-text');
            const loadingSubtext = this.loadingContainer.querySelector('.loading-subtext');
            if (loadingText) loadingText.textContent = message || '正在处理...';
            if (loadingSubtext) loadingSubtext.textContent = '请稍候片刻';
        }
    },

    hideLoading() {
        // 隐藏加载动画
        this.loadingContainer.classList.remove('show');
    },

    showDownloadProgress() {
        this.downloadSection.style.display = 'block';
        this.downloadSection.classList.add('fade-in');
        this.resetDownloadProgress();
        this.downloadSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
    },

    hideDownloadProgress() {
        this.downloadSection.style.display = 'none';
        this.stopDownloadStream();
    },

    resetDownloadProgress() {
        this.downloadStatus.textContent = '0%';
        this.downloadProgressFill.style.width = '0%';
        this.downloadSpeed.textContent = '速度: 0MB/s';
        this.downloadETA.textContent = '剩余: --:--';
        this.downloadSize.textContent = '大小: 0MB / 0MB';
        this.downloadMessage.textContent = '正在下载...';
    },

    // 标签页切换
    showTab(tabName) {
        // 移除所有活跃状态
        document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
        
        // 激活选中的标签页
        document.querySelector(`[onclick="showTab('${tabName}')"]`).classList.add('active');
        document.getElementById(`${tabName}Content`).classList.add('active');
    }
});

/**
 * 页面工作区切换
 */
function enterWorkspace(type, event) {
    if (event) {
        event.preventDefault();
    }
    
    console.log('进入工作区:', type);
    
    // 隐藏首页
    const landingPage = document.getElementById('landingPage');
    if (landingPage) {
        landingPage.style.display = 'none';
    }
    
    // 隐藏所有工作区
    const workspaces = ['workspacePage', 'qaWorkspace', 'searchAgentWorkspace', 'devToolsWorkspace'];
    workspaces.forEach(id => {
        const workspace = document.getElementById(id);
        if (workspace) {
            workspace.style.display = 'none';
        }
    });
    
    // 自动收缩侧边栏（进入工作区时）
    const sidebar = document.getElementById('globalSidebar');
    if (sidebar) {
        sidebar.classList.add('collapsed');
    }
    
    // 根据类型显示对应工作区
    switch(type) {
        case 'notes':
            // AI视频笔记
            const notesWorkspace = document.getElementById('workspacePage');
            if (notesWorkspace) {
                notesWorkspace.style.display = 'grid';
            }
            updateNavActive('notes');
            break;
            
        case 'qa':
            // AI视频问答
            const qaWorkspace = document.getElementById('qaWorkspace');
            if (qaWorkspace) {
                qaWorkspace.style.display = 'grid';
            }
            updateNavActive('qa');
            break;
            
        case 'search-agent':
            // AI视频搜索Agent
            const searchWorkspace = document.getElementById('searchAgentWorkspace');
            if (searchWorkspace) {
                searchWorkspace.style.display = 'grid';
                // 初始化Agent
                if (typeof initSearchAgent === 'function') {
                    initSearchAgent();
                    showAgentWelcomeMessage();
                }
            }
            updateNavActive('search-agent');
            break;
            
        case 'dev-tools':
            // 开发者工具
            const devToolsWorkspace = document.getElementById('devToolsWorkspace');
            if (devToolsWorkspace) {
                devToolsWorkspace.style.display = 'grid';
            }
            updateNavActive('dev-tools');
            break;
            
        default:
            console.warn('未知的工作区类型:', type);
    }
}

/**
 * 切换侧边栏显示/隐藏
 */
function toggleSidebar() {
    const sidebar = document.getElementById('globalSidebar');
    if (sidebar) {
        sidebar.classList.toggle('collapsed');
    }
}

/**
 * 显示首页
 */
function showHomePage(event) {
    if (event) {
        event.preventDefault();
    }
    
    console.log('显示首页');
    
    // 隐藏所有工作区
    const workspaces = ['workspacePage', 'qaWorkspace', 'searchAgentWorkspace', 'devToolsWorkspace'];
    workspaces.forEach(id => {
        const workspace = document.getElementById(id);
        if (workspace) {
            workspace.style.display = 'none';
        }
    });
    
    // 显示首页
    const landingPage = document.getElementById('landingPage');
    if (landingPage) {
        landingPage.style.display = 'flex';
    }
    
    // 更新导航栏活跃状态
    updateNavActive('home');
}

/**
 * 返回首页
 */
function backToLanding() {
    showHomePage();
}

/**
 * 更新导航栏活跃状态
 */
function updateNavActive(activeItem) {
    // 移除所有活跃状态
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // 根据不同的页面类型激活对应的导航项
    let selector;
    switch(activeItem) {
        case 'home':
            selector = '.nav-item[onclick*="showHomePage"]';
            break;
        case 'notes':
            selector = '.nav-item[onclick*="enterWorkspace(\'notes\'"]';
            break;
        case 'qa':
            selector = '.nav-item[onclick*="enterWorkspace(\'qa\'"]';
            break;
        case 'search-agent':
            selector = '.nav-item[onclick*="enterWorkspace(\'search-agent\'"]';
            break;
        case 'dev-tools':
            selector = '.nav-item[onclick*="enterWorkspace(\'dev-tools\'"]';
            break;
    }
    
    if (selector) {
        const activeNav = document.querySelector(selector);
        if (activeNav) {
            activeNav.classList.add('active');
        }
    }
}

/**
 * 首页输入框填充快捷示例
 */
function fillHomeInput(text) {
    const input = document.getElementById('homeInput');
    if (input) {
        input.value = text;
        input.focus();
    }
}

/**
 * 处理首页搜索
 */
function handleHomeSearch() {
    const input = document.getElementById('homeInput');
    const query = input ? input.value.trim() : '';
    
    if (!query) {
        showMessage('请输入您想学习的内容', 'error');
        return;
    }
    
    // 进入搜索Agent工作区
    enterWorkspace('search-agent');
    
    // 等待工作区加载完成后填充查询
    setTimeout(() => {
        const agentInput = document.getElementById('agentInput');
        if (agentInput) {
            agentInput.value = query;
            // 自动发送消息
            sendAgentMessage();
        }
    }, 100);
}

/**
 * 通用消息提示
 */
function showMessage(message, type = 'info') {
    const container = document.getElementById(type === 'error' ? 'errorMessage' : 'successMessage');
    if (!container) return;
    
    container.textContent = message;
    container.style.display = 'block';
    
    // 自动隐藏
    setTimeout(() => {
        container.style.display = 'none';
    }, type === 'error' ? 5000 : 3000);
}

console.log('✅ UI模块已加载');
