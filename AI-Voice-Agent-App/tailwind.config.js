import tailwindcssAnimate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      boxShadow: {
        card: 'var(--shadow-card)',
        overlay: 'var(--shadow-overlay)',
        dropdown: 'var(--shadow-dropdown)',
      },
    },
  },
  plugins: [tailwindcssAnimate],
}
