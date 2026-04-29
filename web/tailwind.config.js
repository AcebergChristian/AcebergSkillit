/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#090909',
          900: '#121212',
          850: '#171717',
          800: '#1d1d1d',
          700: '#2a2a2a',
          600: '#3d3d3d',
        },
        paper: {
          50: '#f7f6f2',
          100: '#f1eee8',
          200: '#e2ddd4',
          300: '#c8c0b3',
        },
        rust: {
          300: '#f0a27f',
          400: '#df835c',
          500: '#cf6c42',
        },
        mint: '#79d2b0',
        sky: '#89b6ff',
      },
      boxShadow: {
        panel: '0 20px 60px rgba(0, 0, 0, 0.35)',
      },
      fontFamily: {
        sans: ['Avenir Next', 'Segoe UI', 'Helvetica Neue', 'sans-serif'],
      },
      backgroundImage: {
        grain: 'radial-gradient(circle at 20% 20%, rgba(255,255,255,0.06), transparent 22%), radial-gradient(circle at 80% 0%, rgba(223,131,92,0.12), transparent 20%), linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0))',
      },
    },
  },
  plugins: [
    function ({ addVariant }) {
      addVariant('light', 'body.light &')
    },
  ],
}
