/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: '#262624',
        surface: '#1f1f1d',
        panel: '#2d2d2a',
        border: '#3a3a37',
        accent: '#e97556',
        'accent-soft': '#2d1a14',
        text: '#ece9e1',
        muted: '#9b978e',
        success: '#6fb38f',
        danger: '#d96a6a',
      },
      fontFamily: {
        body: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SF Mono', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: { sm: '14px', md: '16px', lg: '20px', xl: '28px' },
      lineHeight: { body: '1.6' },
      borderRadius: { sm: '8px', md: '12px', pill: '999px' },
      spacing: { 1: '4px', 2: '8px', 3: '12px', 4: '16px', 6: '24px' },
    },
  },
  plugins: [],
}