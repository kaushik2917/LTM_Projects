"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const pages = [
  ["DS", "/research", "Dataset research"], ["CC", "/", "Command center"],
  ["IN", "/incidents", "Incidents"], ["AG", "/graph", "Attack graph"],
  ["EV", "/evidence", "Evidence intelligence"], ["PV", "/prevention", "Prevention simulator"],
  ["RP", "/reports", "Forensic reports"],
];

export default function Navigation() {
  const pathname = usePathname();
  return <aside className="nav-rail">
    <Link className="brand-mark" href="/" aria-label="FAPT-Guard home">F</Link>
    <nav className="nav-stack" aria-label="Main navigation">
      {pages.map(([short, href, label]) => <Link key={short} href={href} title={label} aria-label={label}
        aria-current={pathname === href ? "page" : undefined}
        className={`nav-item${pathname === href ? " active" : ""}`}>{short}</Link>)}
    </nav>
    <div className="nav-footer" title="Research simulation"><div className="system-dot" /></div>
  </aside>;
}
