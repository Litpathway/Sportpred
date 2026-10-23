"use client";
export default function Error({reset}: {reset: () => void}) { return <div className="empty-state" role="alert"><h1>Something went wrong</h1><p>Please reload this view.</p><button className="button button-outline" onClick={reset}>Try again</button></div>; }
