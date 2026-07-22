import { defineConfig } from 'vitepress'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  lang: 'zh-CN',
  title: 'Question Bank',
  description: 'AI 原生的题库系统 · 使用文档',

  // Project Pages: https://gygy-open.github.io/question-bank/
  base: '/question-bank/',

  lastUpdated: true,
  cleanUrls: true,
  metaChunk: true,

  head: [['link', { rel: 'icon', href: '/question-bank/logo.svg' }]],

  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    logo: '/logo.svg',

    nav: [
      { text: '入门', link: '/guide/introduction', activeMatch: '/guide/' },
      {
        text: '安装部署',
        activeMatch: '/(desktop|server)/',
        items: [
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

      '/desktop/': [
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
      ],

      '/server/': [
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
      ],

      '/features/': [
        {
          text: '功能手册',
          items: [
            { text: '智能导入', link: '/features/import' },
            { text: '题库管理', link: '/features/questions' },
            { text: '知识点体系', link: '/features/knowledge-points' },
            { text: '审核工作流', link: '/features/review-workflow' },
            { text: '组卷 / 试题篮', link: '/features/papers' },
            { text: 'AI 对话', link: '/features/chat' },
            { text: '学科与标签', link: '/features/subjects-and-tags' },
            { text: '文件预览', link: '/features/preview' },
            { text: '操作审计', link: '/features/activity-logs' }
          ]
        }
      ],

      '/admin/': [
        {
          text: '配置',
          items: [
            { text: 'AI 供应商与模型', link: '/admin/ai-config' },
            { text: 'Prompt 模板', link: '/admin/prompts' },
            { text: '系统参数', link: '/admin/system-settings' },
            { text: '用户与权限', link: '/admin/users' }
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

    socialLinks: [
      { icon: 'github', link: 'https://github.com/gygy-open/question-bank' }
    ],

    search: {
      provider: 'local'
    },

    editLink: {
      pattern:
        'https://github.com/gygy-open/question-bank/edit/main/docs/:path',
      text: '在 GitHub 上编辑此页'
    },

    docFooter: {
      prev: '上一页',
      next: '下一页'
    },

    outline: {
      label: '本页目录',
      level: [2, 3]
    },

    lastUpdated: {
      text: '最后更新于'
    },

    footer: {
      message: '基于 AGPL-3.0 许可发布',
      copyright: 'Copyright © 2025-present Question Bank'
    }
  }
})
