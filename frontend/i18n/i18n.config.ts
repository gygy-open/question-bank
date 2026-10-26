export default defineI18nConfig(() => ({
  legacy: false,
  // 缺失的译文回退到中文基准语言，保证逐步迁移期间界面不出现裸 key。
  fallbackLocale: 'zh-CN',
  missingWarn: import.meta.dev,
  fallbackWarn: false,
}))
