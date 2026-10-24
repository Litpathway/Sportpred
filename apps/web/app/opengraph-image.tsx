import { ImageResponse } from "next/og";

export const alt = "SportPredict — Football predictions";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    <div style={{width:"100%",height:"100%",display:"flex",background:"#f5f9fc",color:"#142740",fontFamily:"sans-serif"}}>
      <div style={{width:40,background:"#08a95f",display:"flex"}}/>
      <div style={{display:"flex",flexDirection:"column",padding:"64px 70px",flex:1}}>
        <div style={{display:"flex",justifyContent:"space-between",fontSize:24,borderBottom:"2px solid #dce9e5",paddingBottom:24}}><span>sportpredict</span><span style={{color:"#087b4b",fontSize:18,letterSpacing:3}}>MATCH ANALYSIS</span></div>
        <div style={{display:"flex",flexDirection:"column",fontSize:76,lineHeight:1.05,letterSpacing:-4,marginTop:64}}><span>Football predictions.</span><span>Match analysis.</span></div>
        <div style={{display:"flex",marginTop:40,fontSize:25,color:"#087b4b"}}>Fixtures, probabilities, team form and results.</div>
      </div>
    </div>, size,
  );
}
