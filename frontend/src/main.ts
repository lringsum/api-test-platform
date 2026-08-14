import { createApp } from 'vue'
import Antd from 'ant-design-vue'
import { createPinia } from 'pinia'
import 'ant-design-vue/dist/reset.css'
import 'highlight.js/styles/github.css'
import './styles.css'
import App from './App.vue'
import router from './router'

createApp(App).use(createPinia()).use(router).use(Antd).mount('#app')
