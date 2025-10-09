/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/**/*.js",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        navy: {
          50: '#e8eaed',
          100: '#d1d5db',
          200: '#a3abb7',
          300: '#748193',
          400: '#46576f',
          500: '#1a2332',
          600: '#151c28',
          700: '#10151e',
          800: '#0a0e14',
          900: '#05070a',
        },
        gold: {
          50: '#faf8f3',
          100: '#f5f1e7',
          200: '#ebe3cf',
          300: '#e1d5b7',
          400: '#d7c79f',
          500: '#d4af37',
          600: '#c19b1f',
          700: '#9a7c19',
          800: '#735d12',
          900: '#4c3e0c',
        },
      },
    },
  },
  plugins: [],
}
