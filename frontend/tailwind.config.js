/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        toss: {
          blue: "#3182F6",
          "blue-dark": "#1B64DA",
          gray: {
            50: "#F9FAFB",
            100: "#F2F4F6",
            200: "#E5E8EB",
            300: "#D1D6DB",
            400: "#B0B8C1",
            500: "#8B95A1",
            600: "#6B7684",
            700: "#4E5968",
            800: "#333D4B",
            900: "#191F28",
          },
          red: "#F04452",
          green: "#30B37A",
        },
      },
      borderRadius: {
        toss: "16px",
        "toss-lg": "20px",
      },
      fontFamily: {
        sans: [
          "Pretendard",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      boxShadow: {
        toss: "0 2px 8px rgba(0, 0, 0, 0.04), 0 4px 20px rgba(0, 0, 0, 0.06)",
      },
    },
  },
  plugins: [],
};
