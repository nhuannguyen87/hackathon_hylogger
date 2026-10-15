import "./globals.css";
import HowToRead from "@/components/HowToRead";
import Nav from "@/components/Nav";

export const metadata = {
  title: "GSWA HyLogger Explorer",
  description: "Drill hole mineral logs, uncertainty and anomalies across WA",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en-AU">
      <body>
        <div className="shell">
          <Nav />
          {children}
          <HowToRead />
        </div>
      </body>
    </html>
  );
}
