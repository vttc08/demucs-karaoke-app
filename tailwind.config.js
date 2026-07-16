const forms = require("@tailwindcss/forms");

module.exports = {
  darkMode: "class",
  content: ["./templates/**/*.html", "./static/**/*.js"],
  theme: {
    extend: {
      colors: {
        primary: "#00f2ff",
        secondary: "#3ce36a",
        tertiary: "#ffb950",
        background: "#0e0c1f",
        surface: "#0e0c1f",
        "surface-container": "#19172e",
        "surface-container-low": "#131126",
        "surface-container-lowest": "#000000",
        "surface-container-high": "#1f1c36",
        "surface-container-highest": "#25223e",
        "on-surface": "#e7e2fe",
        "on-surface-variant": "#c9c5d0",
        "outline-variant": "#48455b",
        "tertiary-container": "#8f43fb",
        "on-tertiary-container": "#ffffff",
        "on-primary": "#004343",
        "on-background": "#e7e2fe",
        outline: "#76738b",
        "primary-container": "#00ffff",
        "on-primary-container": "#005d5d",
        error: "#ff6e84"
      },
      fontFamily: {
        headline: ["Space Grotesk", "sans-serif"],
        body: ["Inter", "sans-serif"],
        "login-headline": ["Epilogue", "sans-serif"],
        "login-body": ["Plus Jakarta Sans", "sans-serif"]
      },
      borderRadius: {
        DEFAULT: "0.375rem",
        lg: "0.5rem",
        xl: "0.75rem",
        full: "9999px"
      }
    }
  },
  plugins: [forms]
};
