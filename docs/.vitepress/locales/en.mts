import type { DefaultTheme, LocaleSpecificConfig } from 'vitepress'

const deploySidebar: DefaultTheme.SidebarItem[] = [
  {
    text: 'Desktop',
    items: [
      { text: 'Installation & First Launch', link: '/en/desktop/install' },
      { text: 'Personal Use', link: '/en/desktop/personal' },
      { text: 'LAN Sharing', link: '/en/desktop/lan-sharing' },
      { text: 'Upgrade & Uninstall', link: '/en/desktop/upgrade' }
    ]
  },
  {
    text: 'Server',
    items: [
      { text: 'Docker Compose Deployment', link: '/en/server/docker' },
      { text: 'Configuration Reference', link: '/en/server/configuration' },
      { text: 'Database & Migrations', link: '/en/server/database' },
      { text: 'Operations', link: '/en/server/operations' }
    ]
  }
]

export const en: LocaleSpecificConfig<DefaultTheme.Config> = {
  label: 'English',
  lang: 'en-US',
  link: '/en/',
  title: 'QuestionBank',
  description: 'AI-native question bank · Documentation',

  themeConfig: {
    nav: [
      { text: 'Guide', link: '/en/guide/introduction', activeMatch: '/en/guide/' },
      {
        text: 'Install',
        activeMatch: '/en/(desktop|server)/',
        items: deploySidebar
      },
      { text: 'Configuration', link: '/en/admin/ai-config', activeMatch: '/en/admin/' },
      { text: 'Features', link: '/en/features/import', activeMatch: '/en/features/' },
      { text: 'Development', link: '/en/development/architecture', activeMatch: '/en/development/' }
    ],

    sidebar: {
      '/en/guide/': [
        {
          text: 'Getting Started',
          items: [
            { text: 'Introduction', link: '/en/guide/introduction' },
            { text: 'Editions', link: '/en/guide/editions' }
          ]
        }
      ],

      '/en/desktop/': deploySidebar,
      '/en/server/': deploySidebar,

      '/en/features/': [
        {
          text: 'Features',
          items: [
            { text: 'Smart Import', link: '/en/features/import' },
            { text: 'Question Bank', link: '/en/features/questions' },
            { text: 'Knowledge Points', link: '/en/features/knowledge-points' },
            { text: 'Review Workflow', link: '/en/features/review-workflow' },
            { text: 'AI Assistant', link: '/en/features/chat' },
            { text: 'Subjects & Tags', link: '/en/features/subjects-and-tags' },
            { text: 'File Preview', link: '/en/features/preview' },
            { text: 'Activity Logs', link: '/en/features/activity-logs' },
            { text: 'MCP Access', link: '/en/features/mcp' }
          ]
        }
      ],

      '/en/admin/': [
        {
          text: 'Configuration',
          items: [
            { text: 'AI Providers & Models', link: '/en/admin/ai-config' },
            { text: 'Prompt Templates', link: '/en/admin/prompts' },
            { text: 'System Settings', link: '/en/admin/system-settings' },
            { text: 'Users', link: '/en/admin/users' },
            { text: 'Permissions & Roles', link: '/en/admin/permissions' }
          ]
        }
      ],

      '/en/development/': [
        {
          text: 'Development',
          items: [
            { text: 'Architecture', link: '/en/development/architecture' },
            { text: 'Local Development', link: '/en/development/local-setup' },
            { text: 'Backend Conventions', link: '/en/development/backend' },
            { text: 'Frontend Conventions', link: '/en/development/frontend' },
            { text: 'Contributing', link: '/en/development/contributing' }
          ]
        }
      ]
    },

    editLink: {
      pattern: 'https://github.com/gygy-open/question-bank/edit/main/docs/:path',
      text: 'Edit this page on GitHub'
    },

    outline: { level: [2, 3] },

    footer: {
      message: 'Released under the AGPL-3.0 License',
      copyright: 'Copyright © 2025-present QuestionBank'
    }
  }
}
