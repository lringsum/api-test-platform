<script setup lang="ts">
import { computed, ref } from 'vue'
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import { platformApi } from '../services/platform'

const route = useRoute()
const router = useRouter()
const forbidden = computed(() => route.name === 'forbidden')
const invalidCredentials = computed(() => route.query.error === 'invalid_credentials')
const username = ref('')
const password = ref('')
const loading = ref(false)
const submitError = ref('')

async function login() {
  submitError.value = ''
  loading.value = true
  try {
    await platformApi.login({ username: username.value, password: password.value })
    const rawNext = typeof route.query.next === 'string' ? route.query.next : '/'
    const parsedNext = rawNext.startsWith('http') ? new URL(rawNext).pathname + new URL(rawNext).search : rawNext
    await router.replace(parsedNext.startsWith('/app/') ? parsedNext.replace('/app', '') : '/')
  } catch {
    submitError.value = '用户名或密码不正确，请重试。'
    message.error('用户名或密码不正确')
  } finally {
    loading.value = false
  }
}
async function logout() { await platformApi.logout(); await router.replace('/login') }
</script>

<template>
  <main class="auth-page">
    <div class="auth-grid" aria-hidden="true">
      <i class="grid-line line-a" /><i class="grid-line line-b" /><i class="grid-line line-c" />
      <i class="grid-node node-a" /><i class="grid-node node-b" /><i class="grid-node node-c" /><i class="grid-node node-d" />
      <span class="radar radar-a" /><span class="radar radar-b" />
      <span class="trace-copy copy-a">QA-01<br><b>用例库</b></span><span class="trace-copy copy-b">QA-02<br><b>执行中</b></span><span class="trace-copy copy-c">QA-03<br><b>缺陷追踪</b></span>
    </div>

    <header class="brand-mark"><span class="brand-icon"><svg viewBox="0 0 40 40" aria-hidden="true"><path d="M5 22c4-8 8 4 13-1s8-8 17-1" /></svg></span><span><b>FLOAT QA</b><small>测试协作平台</small></span></header>

    <section v-if="!forbidden" class="auth-intro">
      <p class="intro-kicker">QUALITY ASSURANCE PLATFORM</p>
      <h1>让每一次测试，<br>都有清晰的落点。</h1>
      <p class="intro-copy">统一权限、规范流程、可追溯可度量，<br>让质量管理回归确定性。</p>
    </section>

    <section v-if="!forbidden" class="login-sheet">
      <span class="sheet-layer layer-one" /><span class="sheet-layer layer-two" />
      <div class="sheet-content">
        <div class="sheet-id">IDX<br><b>01</b></div>
        <p class="sheet-eyebrow">欢迎回来</p>
        <h2>登录 FLOAT QA</h2>
        <a-alert v-if="invalidCredentials || submitError" class="login-alert" type="error" show-icon :message="submitError || '用户名或密码不正确，请重试。'" />
        <a-form class="login-form" layout="vertical" @submit.prevent="login">
          <a-form-item label="用户名" name="username" required><a-input v-model:value="username" size="large" autocomplete="username" placeholder="请输入用户名"><template #prefix><UserOutlined /></template></a-input></a-form-item>
          <a-form-item label="密码" name="password" required><a-input-password v-model:value="password" size="large" autocomplete="current-password" placeholder="请输入密码"><template #prefix><LockOutlined /></template></a-input-password></a-form-item>
          <a-button class="login-submit" type="primary" html-type="submit" size="large" :loading="loading">登录</a-button>
        </a-form>
        <div class="sheet-footer"><SafetyCertificateOutlined /><span>账号权限由平台统一管理</span><span class="footer-index">IDX<br><b>02</b></span></div>
      </div>
    </section>

    <section v-else class="forbidden-sheet">
      <p class="sheet-eyebrow">ACCESS CONTROL</p><h2>暂时无法访问</h2>
      <p>当前账号没有访问此功能所需的权限。请联系管理员调整角色或项目成员范围。</p>
      <a-space class="mt-8"><a-button type="primary" @click="router.push('/')">返回工作台</a-button><a-button @click="logout">退出当前账号</a-button></a-space>
    </section>
  </main>
</template>

<style scoped>
.auth-page { --paper:#fff; --ink:#0e1d4a; --blue:#1769f0; position:relative; min-height:100vh; overflow:hidden; background:radial-gradient(circle at 66% 46%, rgba(201,222,255,.72), transparent 32%), radial-gradient(circle at 17% 46%, rgba(230,240,255,.95), transparent 26%), #f8fbff; color:var(--ink); }
.auth-page::after { position:absolute; inset:0; z-index:0; background-image:radial-gradient(rgba(26,82,170,.12) .55px, transparent .6px); background-size:5px 5px; content:""; opacity:.2; pointer-events:none; }
.brand-mark { position:absolute; z-index:2; top:5.5vh; left:4.4vw; display:flex; align-items:center; gap:12px; letter-spacing:.08em; animation:float-in .6s ease-out both; }
.brand-mark b { display:block; font-size:23px; line-height:1; font-weight:800; }.brand-mark small { display:block; margin-top:5px; font-size:12px; font-weight:600; letter-spacing:.04em; }.brand-icon { display:grid; width:44px; height:44px; place-items:center; border-radius:8px; background:linear-gradient(145deg,#3385ff,#0758df); box-shadow:0 8px 18px rgba(23,105,240,.24); }.brand-icon svg { width:32px; }.brand-icon path { fill:none; stroke:#fff; stroke-linecap:round; stroke-width:2.1; }
.auth-intro { position:absolute; z-index:2; top:31%; left:14.5%; animation:float-in .7s .12s ease-out both; }.intro-kicker { margin:0 0 28px; color:#9ec1fc; font-size:10px; font-weight:700; letter-spacing:.18em; }.auth-intro h1 { margin:0; font-family:"Noto Serif SC",STSong,serif; font-size:clamp(37px,3.75vw,60px); font-weight:700; line-height:1.46; letter-spacing:.03em; text-shadow:0 2px 9px rgba(255,255,255,.6); }.intro-copy { margin:30px 0 0; color:#7795c3; font-size:17px; font-weight:500; line-height:1.8; }
.auth-grid { position:absolute; inset:0; z-index:1; opacity:.54; }.grid-line { position:absolute; height:1px; transform-origin:left center; background:linear-gradient(90deg,rgba(115,170,252,.55),rgba(115,170,252,.05)); }.line-a { top:31%; left:7%; width:45%; transform:rotate(29deg); }.line-b { top:77%; left:15%; width:39%; transform:rotate(10deg); }.line-c { top:84%; left:37%; width:31%; transform:rotate(-61deg); }.grid-node { position:absolute; width:10px; height:10px; border:3px solid #b6d1fc; border-radius:50%; background:#4a94fa; box-shadow:0 0 0 5px rgba(138,185,255,.09); }.node-a { top:30.5%; left:7%; }.node-b { top:55%; left:49%; }.node-c { top:76.5%; left:15%; }.node-d { top:83%; left:37%; }.radar { position:absolute; width:108px; height:108px; border:1px solid #cfe2ff; border-radius:50%; }.radar::before,.radar::after { position:absolute; border:1px solid #d8e8ff; border-radius:50%; content:""; }.radar::before { inset:17px; }.radar::after { inset:42px; }.radar-a { top:25.5%; left:3.7%; }.radar-b { top:68.7%; left:9.6%; width:144px; height:144px; }.trace-copy { position:absolute; color:#9fc3fe; font-size:13px; font-weight:700; line-height:1.6; }.trace-copy b { font-weight:600; }.copy-a { top:23.5%; left:11.7%; }.copy-b { top:67.8%; left:20.7%; }.copy-c { top:83.8%; left:41.5%; }
.login-sheet { position:absolute; z-index:3; top:18.8%; right:12.4%; width:min(485px,38vw); min-width:420px; animation:sheet-in .8s .15s cubic-bezier(.2,.85,.25,1) both; }.sheet-layer { position:absolute; display:block; border:1px solid rgba(70,140,247,.24); background:rgba(255,255,255,.72); box-shadow:0 16px 32px rgba(31,75,139,.12); }.layer-one { top:22px; right:-7px; bottom:-25px; left:-23px; }.layer-two { top:5px; right:25px; bottom:-49px; left:25px; transform:rotate(-10deg); }.sheet-content { position:relative; min-height:610px; padding:72px 54px 44px; clip-path:polygon(0 0,89% 0,100% 10%,100% 100%,0 100%); border:1px solid rgba(213,226,248,.92); background:rgba(255,255,255,.96); box-shadow:0 20px 42px rgba(31,75,139,.13); }.sheet-content::before,.sheet-content::after { position:absolute; width:2px; background:#4f97ff; content:""; }.sheet-content::before { top:28px; bottom:28px; left:-1px; }.sheet-content::after { top:64px; right:21px; height:510px; opacity:.65; }.sheet-id { position:absolute; top:80px; right:44px; color:#80aeff; font-size:12px; line-height:1.25; text-align:center; }.sheet-id b,.footer-index b { font-size:15px; }.sheet-eyebrow { margin:0 0 9px; color:#7baafc; font-size:11px; font-weight:700; letter-spacing:.18em; }.sheet-content h2,.forbidden-sheet h2 { margin:0; font-family:"Noto Serif SC",STSong,serif; font-size:36px; font-weight:700; letter-spacing:.025em; }.login-alert { margin-top:24px; }.login-form { margin-top:46px; }.login-form :deep(.ant-form-item-label > label) { height:auto; color:#273a68; font-size:16px; font-weight:600; }.login-form :deep(.ant-input-affix-wrapper),.login-form :deep(.ant-input) { min-height:59px; border-radius:10px; background:#fff; font-size:16px; }.login-form :deep(.ant-input-prefix) { margin-right:10px; color:#8eb4ef; }.login-submit { width:100%; height:63px; margin-top:7px; border-radius:8px; font-size:18px; font-weight:600; letter-spacing:.12em; background:#1769f0; box-shadow:0 10px 22px rgba(23,105,240,.2); }.sheet-footer { position:absolute; right:54px; bottom:42px; left:54px; display:flex; align-items:center; gap:10px; color:#87a6d8; font-size:15px; }.sheet-footer :deep(svg) { color:#5c9dff; font-size:23px; }.footer-index { margin-left:auto; color:#80aeff; font-size:11px; line-height:1.2; text-align:center; }.forbidden-sheet { position:absolute; z-index:3; top:50%; left:50%; width:min(480px,calc(100vw - 40px)); padding:54px; transform:translate(-50%,-50%); border:1px solid #dbe8fb; background:#fff; box-shadow:0 22px 60px rgba(34,74,134,.15); }.forbidden-sheet p:not(.sheet-eyebrow) { color:#687c9e; line-height:1.8; }
@keyframes float-in { from { opacity:0; transform:translateY(16px); } to { opacity:1; transform:translateY(0); } } @keyframes sheet-in { from { opacity:0; transform:translate(32px,14px) rotate(.8deg); } to { opacity:1; transform:translate(0) rotate(0); } }
@media (max-width:900px) { .login-sheet { right:6vw; width:48vw; min-width:390px; }.auth-intro { left:7vw; }.auth-intro h1 { font-size:42px; }.intro-copy { font-size:15px; } }
@media (max-width:720px) { .auth-page { min-height:100dvh; overflow:auto; }.brand-mark { top:28px; left:28px; }.auth-intro { position:relative; top:auto; left:auto; padding:128px 28px 30px; }.intro-kicker,.intro-copy,.auth-grid { display:none; }.auth-intro h1 { font-size:32px; line-height:1.45; }.login-sheet { position:relative; top:auto; right:auto; width:auto; min-width:0; margin:0 22px 42px; }.sheet-content { min-height:0; padding:52px 30px 94px; }.sheet-content h2 { font-size:29px; }.login-form { margin-top:32px; }.sheet-footer { right:30px; bottom:30px; left:30px; font-size:13px; }.sheet-id { top:58px; right:28px; } }
</style>
