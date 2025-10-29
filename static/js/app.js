/**
 * ViNote - AI视频笔记应用
 * 主入口文件 - 模块化版本
 */

// 全局变量
let app;

// 页面加载完成后初始化应用
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 开始初始化ViNote应用...');
    
    // 创建应用实例
    app = new VideoTranscriber();
    
    // 检查并初始化搜索Agent模块
    if (typeof initSearchAgent === 'function') {
        console.log('✅ 搜索Agent模块已加载');
    } else {
        console.warn('⚠️ 搜索Agent模块未加载');
    }
    
    // 首页默认展开侧边栏，移除collapsed类
    const sidebar = document.getElementById('globalSidebar');
    if (sidebar) {
        sidebar.classList.remove('collapsed');
    }
    
    // 恢复页面状态（如果有缓存）
    restorePageState();
    
    console.log('✅ ViNote应用初始化完成');
});

// 页面卸载前保存状态
window.addEventListener('beforeunload', () => {
    savePageState();
});

// 点击页面其他地方关闭联系卡片
document.addEventListener('click', (e) => {
    const contactAuthor = document.querySelector('.contact-author');
    const card = document.getElementById('contactCard');
    if (contactAuthor && card && !contactAuthor.contains(e.target)) {
        card.classList.remove('show');
    }
});

console.log('✅ 主入口文件已加载');
