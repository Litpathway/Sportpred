import Link from "next/link";
export default function NotFound() { return <div className="empty-state"><h1>Page not found</h1><p>This page isn’t part of the workspace.</p><Link className="text-link" href="/">Return to overview</Link></div>; }
