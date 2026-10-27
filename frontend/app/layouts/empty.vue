<template>
  <div>
    <!-- 登录、注册、初始化等无侧边栏页面共用：语言切换固定在右上角，首次访问的用户也能找到。 -->
    <div class="fixed right-3 top-3 z-50">
      <LanguageSwitcher />
    </div>
    <slot />
  </div>
</template>
