/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          50: '#f6f7fb',
          100: '#eceef4',
          200: '#d6d9e6',
          300: '#b4b8ce',
          400: '#7c80a1',
          500: '#55597c',
          600: '#3f4361',
          700: '#2f324d',
          800: '#212438',
          900: '#161927',
          950: '#0f111b',
        },
        accent: {
          50: '#ebf4ff',
          100: '#d7e9ff',
          200: '#b3d4ff',
          300: '#86b7ff',
          400: '#5692ff',
          500: '#346dff',
          600: '#1f4dff',
          700: '#1a3ee6',
          800: '#1835b8',
          900: '#192f90',
        },
        success: '#22c55e',
        danger: '#ef4444',
        warning: '#f59e0b',
      },
      fontFamily: {
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'Oxygen',
          'Ubuntu',
          'Cantarell',
          'Fira Sans',
          'Droid Sans',
          'Helvetica Neue',
          'sans-serif',
        ],
        mono: ['JetBrains Mono', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      borderRadius: {
        xl: '1rem',
      },
    },
  },
  plugins: [],
}

