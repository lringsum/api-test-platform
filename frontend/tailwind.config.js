/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Noto Serif SC"', 'STSong', 'serif'],
        sans: ['"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
      },
      colors: {
        ink: '#11204a',
        canvas: '#f6faff',
        line: '#e1ebfa',
        brand: '#1769f0',
      },
      boxShadow: {
        panel: '0 12px 40px rgba(33, 79, 147, 0.06)',
      },
    },
  },
  plugins: [],
}
