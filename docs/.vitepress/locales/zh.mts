import type { DefaultTheme, LocaleSpecificConfig } from 'vitepress'

const deploySidebar: DefaultTheme.SidebarItem[] = [
  {
    text: '桌面版',
    items: [
      { text: '安装与首次启动', link: '/desktop/install' },
      { text: '个人使用', link: '/desktop/personal' },
      { text: '局域网共享', link: '/desktop/lan-sharing' },
      { text: '升级与卸载', link: '/desktop/upgrade' }
    ]
  },
  {
    text: '服务器版',
    items: [
      { text: 'Docker Compose 部署', link: '/server/docker' },
      { text: '配置参考', link: '/server/configuration' },
      { text: '数据库与迁移', link: '/server/database' },
      { text: '运维', link: '/server/operations' }
    ]
  }
]

export const zh: LocaleSpecificConfig<DefaultTheme.Config> = {
  label: '简体中文',
  lang: 'zh-CN',
  title: 'QuestionBank',
  description: 'AI 原生的题库系统 · 使用文档',

  themeConfig: {
    nav: [
      { text: '入门', link: '/guide/introduction', activeMatch: '/guide/' },
      {
        text: '安装部署',
        activeMatch: '/(desktop|server)/',
        items: deploySidebar
      },
      { text: '配置', link: '/admin/ai-config', activeMatch: '/admin/' },
      { text: '功能', link: '/features/import', activeMatch: '/features/' },
      { text: '开发', link: '/development/architecture', activeMatch: '/development/' }
    ],

    sidebar: {
      '/guide/': [
        {
          text: '入门',
          items: [
            { text: '产品简介', link: '/guide/introduction' },
            { text: '版本与选型', link: '/guide/editions' }
          ]
        }
      ],

      '/desktop/': deploySidebar,
      '/server/': deploySidebar,

      '/features/': [
        {
          text: '功能手册',
          items: [
            { text: '智能导入', link: '/features/import' },
            { text: '题库管理', link: '/features/questions' },
            { text: '知识点体系', link: '/features/knowledge-points' },
            { text: '审核工作流', link: '/features/review-workflow' },
            { text: 'AI 对话', link: '/features/chat' },
            { text: '学科与标签', link: '/features/subjects-and-tags' },
            { text: '文件预览', link: '/features/preview' },
            { text: '操作审计', link: '/features/activity-logs' },
            { text: 'MCP 接入', link: '/features/mcp' }
          ]
        }
      ],

      '/admin/': [
        {
          text: '配置',
          items: [
            { text: 'AI 服务商与模型', link: '/admin/ai-config' },
            { text: 'Prompt 模板', link: '/admin/prompts' },
            { text: '系统参数', link: '/admin/system-settings' },
            { text: '用户管理', link: '/admin/users' },
            { text: '权限与角色', link: '/admin/permissions' }
          ]
        }
      ],

      '/development/': [
        {
          text: '开发',
          items: [
            { text: '架构总览', link: '/development/architecture' },
            { text: '本地开发', link: '/development/local-setup' },
            { text: '后端约定', link: '/development/backend' },
            { text: '前端约定', link: '/development/frontend' },
            { text: '贡献指南', link: '/development/contributing' }
          ]
        }
      ]
    },

    editLink: {
      pattern: 'https://github.com/gygy-open/question-bank/edit/main/docs/:path',
      text: '在 GitHub 上编辑此页'
    },

    docFooter: { prev: '上一页', next: '下一页' },
    outline: { label: '本页目录', level: [2, 3] },
    lastUpdated: { text: '最后更新于' },
    returnToTopLabel: '回到顶部',
    sidebarMenuLabel: '菜单',
    darkModeSwitchLabel: '外观',
    lightModeSwitchTitle: '切换到浅色模式',
    darkModeSwitchTitle: '切换到深色模式',
    langMenuLabel: '切换语言',
    notFound: {
      title: '页面未找到',
      quote: '你访问的页面不存在或已被移动。',
      linkLabel: '返回首页',
      linkText: '返回首页'
    },

    footer: {
      message: '基于 AGPL-3.0 许可发布',
      copyright: 'Copyright © 2025-present QuestionBank'
    }
  }
}

export const zhSearch: DefaultTheme.LocalSearchOptions['locales'] = {
  root: {
    translations: {
      button: { buttonText: '搜索文档', buttonAriaLabel: '搜索文档' },
      modal: {
        displayDetails: '显示详细列表',
        resetButtonTitle: '清除查询条件',
        backButtonTitle: '关闭搜索',
        noResultsText: '没有找到相关结果',
        footer: {
          selectText: '选择',
          selectKeyAriaLabel: '回车',
          navigateText: '切换',
          navigateUpKeyAriaLabel: '上方向键',
          navigateDownKeyAriaLabel: '下方向键',
          closeText: '关闭',
          closeKeyAriaLabel: 'Esc'
        }
      }
    }
  }
}
