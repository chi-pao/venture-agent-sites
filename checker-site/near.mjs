// 「近くの似た取引」の選び方。築年数・土地・建物の広さが近いことに加えて、家に近い町の取引を優先する。
// 町の位置は area/<code>/towns.json（tools/build_town_coords.py、公示地価・地価調査の地点から）。
// 位置が分からない町どうしは、公示地価（land-prices.json）の差で、地域の性格が近いかを見る。
export const kmBetween=(a,b)=>{const r=Math.PI/180,dy=(a[0]-b[0])*111.0,dx=(a[1]-b[1])*111.0*Math.cos(a[0]*r);return Math.hypot(dx,dy);};
export function placeTerm(s,home){
  if(home.district&&s[2]===home.district)return {cost:0,km:0};
  const there=home.towns?.[s[2]];
  if(home.pos&&there){const km=kmBetween(home.pos,there);return {cost:(km/2)**2,km};}
  const lp=home.landPrices?.[s[2]];
  if(home.landPrice>0&&lp>0)return {cost:(Math.log(lp/home.landPrice)/.25)**2+1,km:null};
  return {cost:2.5,km:null};
}
export function nearestSales(sales,d,home,n=5){
  const age=2026-d.year;
  const size=s=>{const a=s[6]?2026-s[6]:null;return (a==null?1.5:Math.abs(a-age)/8)**2+(s[4]&&d.landArea?Math.log(s[4]/d.landArea)/.35:1)**2+(s[5]&&d.buildingArea?Math.log(s[5]/d.buildingArea)/.25:1)**2;};
  return sales.map(s=>{const p=placeTerm(s,home);return {s,km:p.km,cost:size(s)+p.cost};}).sort((x,y)=>x.cost-y.cost).slice(0,n);
}
