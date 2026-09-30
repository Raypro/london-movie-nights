const $ = (id) => document.getElementById(id);
const FALLBACK_CINEMAS = [
  {id:'silvercity',name:'SilverCity London',url:'https://www.cineplex.com/theatre/silvercity-london-cinemas'},
  {id:'westmount',name:'Westmount VIP',url:'https://www.cineplex.com/theatre/cineplex-odeon-westmount-cinemas-and-vip'},
  {id:'landmark',name:'Landmark London',url:'https://www.landmarkcinemas.com/showtimes/london'},
  {id:'imagine',name:'Imagine Cinemas London',url:'https://imaginecinemas.com/cinema/london/'},
  {id:'hyland',name:'Hyland Cinema',url:'https://www.hylandcinema.com/movie-calendar'}
];
const state = {data:null,date:null,cinema:'all',view:'showtimes'};
const dayFormatter = new Intl.DateTimeFormat('en-CA',{timeZone:'America/Toronto',weekday:'short',month:'short',day:'numeric'});
const longDayFormatter = new Intl.DateTimeFormat('en-CA',{timeZone:'America/Toronto',weekday:'long',month:'long',day:'numeric'});
const dateFormatter = new Intl.DateTimeFormat('en-CA',{timeZone:'America/Toronto',month:'short',day:'numeric',year:'numeric'});
const checkedFormatter = new Intl.DateTimeFormat('en-CA',{timeZone:'America/Toronto',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});

function element(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node;}
function safeHref(value){try{const url=new URL(value);return url.protocol==='https:'?url.href:null;}catch{return null;}}
function localDate(iso){return new Date(`${iso}T12:00:00Z`);}
function shortDate(iso){return dayFormatter.format(localDate(iso));}
function longDate(iso){return longDayFormatter.format(localDate(iso));}
function releaseDate(iso){return dateFormatter.format(localDate(iso));}
function timeLabel(value){const [hour,minute]=value.split(':').map(Number);return `${(hour%12)||12}:${String(minute).padStart(2,'0')} ${hour>=12?'pm':'am'}`;}
function torontoNow(){const parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/Toronto',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date());const value=Object.fromEntries(parts.map(x=>[x.type,x.value]));return {date:`${value.year}-${value.month}-${value.day}`,minute:Number(value.hour)*60+Number(value.minute)};}
function futureScreenings(){const now=torontoNow();return (state.data?.screenings||[]).filter(item=>item.date>now.date||(item.date===now.date&&(Number(item.time.slice(0,2))*60+Number(item.time.slice(3,5)))>now.minute));}
function cinemaName(id){return (state.data?.cinemas||FALLBACK_CINEMAS).find(x=>x.id===id)?.name||id;}

function setView(view){
  state.view=view;
  $('showtimes-view').hidden=view!=='showtimes';$('horror-view').hidden=view!=='horror';
  for(const [name,id] of [['showtimes','tab-showtimes'],['horror','tab-horror']]){
    const active=name===view;$(id).classList.toggle('is-active',active);$(id).setAttribute('aria-selected',String(active));
  }
  if(view==='horror')renderHorror();
  window.scrollTo({top:0,behavior:'smooth'});
}

function renderDates(){
  const rail=$('dates');rail.replaceChildren();
  for(const iso of state.data.dates){
    const button=element('button','date-chip');button.type='button';button.setAttribute('aria-label',longDate(iso));
    const [weekday,rest]=shortDate(iso).split(', ');button.append(element('span','',weekday),element('strong','',String(Number(iso.slice(-2)))));
    button.title=rest||shortDate(iso);button.classList.toggle('is-active',iso===state.date);button.setAttribute('aria-pressed',String(iso===state.date));
    button.addEventListener('click',()=>{state.date=iso;const url=new URL(location.href);url.searchParams.set('date',iso);history.replaceState(null,'',url);renderDates();renderDay();});
    rail.append(button);
  }
}

function renderFilters(){
  const host=$('cinema-filters');host.replaceChildren();
  const choices=[{id:'all',name:'All cinemas'},...state.data.cinemas];
  for(const choice of choices){
    const button=element('button','cinema-filter',choice.name);button.type='button';button.classList.toggle('is-active',choice.id===state.cinema);button.setAttribute('aria-pressed',String(choice.id===state.cinema));
    button.addEventListener('click',()=>{state.cinema=choice.id;renderFilters();renderDay();});host.append(button);
  }
  $('clear-filter').hidden=state.cinema==='all';
}

function groupFilms(items){
  const map=new Map();
  for(const item of items){if(!map.has(item.key))map.set(item.key,{key:item.key,title:item.title,items:[],genres:new Set()});const film=map.get(item.key);film.items.push(item);for(const genre of item.genres||[])film.genres.add(genre);}
  return [...map.values()].sort((a,b)=>{
    const firstA=a.items.map(x=>x.time).sort()[0],firstB=b.items.map(x=>x.time).sort()[0];
    return firstA.localeCompare(firstB)||a.title.localeCompare(b.title);
  });
}

function renderMovieCard(film){
  const card=element('article','movie-card');
  const top=element('div','movie-card__top');top.append(element('h3','',film.title));
  if(film.items.some(x=>(x.genres||[]).some(g=>g.toLowerCase().includes('horror'))))top.append(element('span','movie-card__tag','Horror'));
  card.append(top);
  const genres=[...film.genres].filter(Boolean).slice(0,3);card.append(element('p','movie-card__genre',genres.join(' · ')||'On screen in London'));
  const theatreIds=[...new Set(film.items.map(x=>x.theatre))].sort((a,b)=>cinemaName(a).localeCompare(cinemaName(b)));
  for(const id of theatreIds){
    const venue=element('div','venue');const heading=element('div','venue__heading');heading.append(element('strong','',cinemaName(id)));
    const cinema=state.data.cinemas.find(x=>x.id===id);const website=element('a','', 'Cinema ↗');website.href=safeHref(cinema?.url)||'#';website.target='_blank';website.rel='noopener noreferrer';heading.append(website);venue.append(heading);
    const times=element('div','time-grid');
    for(const item of film.items.filter(x=>x.theatre===id).sort((a,b)=>a.time.localeCompare(b.time)||a.format.localeCompare(b.format))){
      const link=element('a','time-chip');link.href=safeHref(item.bookingUrl||item.detailUrl)||website.href;link.target='_blank';link.rel='noopener noreferrer';
      link.setAttribute('aria-label',`${timeLabel(item.time)}, ${cinemaName(id)}, ${film.title}${item.format?`, ${item.format}`:''}${item.soldOut?', sold out':''}. Open booking or details.`);
      link.append(element('strong','',timeLabel(item.time)),element('small','',item.soldOut?'Sold out':item.format||'Tickets ↗'));
      if(item.soldOut)link.classList.add('is-soldout');times.append(link);
    }
    venue.append(times);card.append(venue);
  }
  return card;
}

function renderDay(){
  if(!state.data)return;
  const items=futureScreenings().filter(item=>item.date===state.date&&(state.cinema==='all'||item.theatre===state.cinema));
  const films=groupFilms(items);$('day-heading').replaceChildren(element('strong','',longDate(state.date)),element('span','',`${films.length} ${films.length===1?'film':'films'} with posted times`));
  const host=$('movie-list');host.replaceChildren();
  if(films.length){for(const film of films)host.append(renderMovieCard(film));}
  else{const empty=element('div','empty-state');empty.append(element('strong','','No times captured here yet'),element('p','','This date may not be posted, or a cinema may be unavailable. Check the live links below.'));host.append(empty);}
  const notChecked=state.data.cinemas.filter(x=>state.cinema==='all'||x.id===state.cinema).filter(x=>!x.datesChecked.includes(state.date));
  const notes=notChecked.map(x=>`${x.name}: ${x.status==='link_only'?'check live listings':x.status==='unavailable'?'source unavailable':'date not confirmed by source'}`);
  $('date-source-note').textContent=notes.length?`Coverage note · ${notes.join(' · ')}`:'Times are linked to their cinema booking or film page.';
}

function horrorCard(pick,local){
  const card=element('article','horror-card');card.append(element('span','horror-card__kind',pick.kind||'Horror'));
  card.append(element('h3','',pick.title),element('p','',pick.note||'A darker pick for movie night.'));
  const bottom=element('div','horror-card__bottom');
  let statusText;
  if(local){statusText=`London: ${shortDate(local.date)} · ${cinemaName(local.theatre)}`;}
  else if(pick.canadianReleaseDate){statusText=`Canada: ${releaseDate(pick.canadianReleaseDate)} · London time unconfirmed`;}
  else{statusText='London time unconfirmed';}
  bottom.append(element('span','horror-card__status',statusText));
  if(local){
    const action=element('button','horror-card__action','See times →');action.type='button';
    action.addEventListener('click',()=>{state.date=local.date;state.cinema='all';renderDates();renderFilters();renderDay();setView('showtimes');});bottom.append(action);
  }else{
    const action=element('a','horror-card__action','Film details ↗');action.href=safeHref(pick.sourceUrl)||'#';action.target='_blank';action.rel='noopener noreferrer';bottom.append(action);
  }
  card.append(bottom);return card;
}

function renderHorrorGroup(hostId,heading,entries){
  const host=$(hostId);host.replaceChildren();if(!entries.length)return;
  host.className='horror-group';host.append(element('h3','horror-group__heading',heading));
  const grid=element('div','horror-grid');for(const entry of entries)grid.append(horrorCard(entry.pick,entry.local));host.append(grid);
}

function renderHorror(){
  if(!state.data)return;
  const available=futureScreenings();const picks=[...state.data.picks];
  const pickedKeys=new Set(picks.flatMap(x=>x.keys));
  for(const item of available){
    if(pickedKeys.has(item.key)||!(item.genres||[]).some(g=>g.toLowerCase().includes('horror')))continue;
    picks.push({title:item.title,kind:'Horror',note:'A horror film with a posted London showtime.',sourceUrl:item.detailUrl,keys:[item.key],canadianReleaseDate:null});pickedKeys.add(item.key);
  }
  const playing=[],coming=[];
  for(const pick of picks){
    const local=available.filter(x=>pick.keys.includes(x.key)).sort((a,b)=>a.date.localeCompare(b.date)||a.time.localeCompare(b.time))[0]||null;
    (local?playing:coming).push({pick,local});
  }
  playing.sort((a,b)=>a.local.date.localeCompare(b.local.date)||a.local.time.localeCompare(b.local.time));
  coming.sort((a,b)=>(a.pick.canadianReleaseDate||'9999').localeCompare(b.pick.canadianReleaseDate||'9999'));
  renderHorrorGroup('horror-playing','Booked in London',playing);
  renderHorrorGroup('horror-coming','Coming up · London unconfirmed',coming);
}

function renderSources(){
  const host=$('source-list');host.replaceChildren();
  const cinemas=state.data?.cinemas||FALLBACK_CINEMAS.map(x=>({...x,status:'unavailable',datesChecked:[]}));
  const labels={ok:'Updated',partial:'Partial',unavailable:'Unavailable',link_only:'Check live'};
  for(const cinema of cinemas){
    const row=element('a','source-row');row.href=safeHref(cinema.url)||'#';row.target='_blank';row.rel='noopener noreferrer';
    const left=element('div');left.append(element('strong','',cinema.name));
    left.append(element('small','',cinema.status==='ok'?`${cinema.datesChecked.length} dates checked`:cinema.status==='link_only'?'Live showtimes on cinema site':cinema.note||'Some times may be missing'));
    const side=element('div','source-row__side');const badge=element('span','source-status',labels[cinema.status]||'Check live');if(cinema.status!=='ok')badge.classList.add('is-warning');side.append(badge,element('span','source-row__arrow','↗'));row.append(left,side);host.append(row);
  }
}

function renderFreshness(){
  const generated=new Date(state.data.generatedAt);const hours=(Date.now()-generated.getTime())/3600000;
  $('updated-line').textContent=`Last checked ${checkedFormatter.format(generated)} · London time`;
  const notice=$('notice');
  if(!Number.isFinite(hours)||hours>30){notice.textContent='These listings have not refreshed recently. Please check the cinema’s live page before making plans.';notice.hidden=false;}
  else if(!state.data.screenings.length){notice.textContent='Showtimes are temporarily unavailable. The cinema links below still have live listings.';notice.hidden=false;}
  else{notice.hidden=true;}
}

async function load(){
  try{
    const response=await fetch('./data.json',{cache:'no-store'});if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const data=await response.json();if(!Array.isArray(data.dates)||!Array.isArray(data.cinemas)||!Array.isArray(data.screenings)||!Array.isArray(data.picks))throw new Error('Invalid listings data');
    state.data=data;const requested=new URLSearchParams(location.search).get('date');const today=torontoNow().date;
    state.date=data.dates.includes(requested)?requested:(data.dates.includes(today)?today:data.dates.find(x=>x>=today)||data.dates[0]);
    renderFreshness();renderDates();renderFilters();renderDay();renderHorror();renderSources();
  }catch(error){
    $('updated-line').textContent='Listings unavailable';$('notice').textContent='The guide could not load its latest listings. Open a cinema below for live showtimes.';$('notice').hidden=false;renderSources();
    $('day-heading').textContent='Showtimes are unavailable';const empty=element('div','empty-state');empty.append(element('strong','','Please check a cinema directly'),element('p','','The five live cinema links are below.'));$('movie-list').replaceChildren(empty);
    console.error('Movie data load failed',error);
  }
}

$('tab-showtimes').addEventListener('click',()=>setView('showtimes'));
$('tab-horror').addEventListener('click',()=>setView('horror'));
$('clear-filter').addEventListener('click',()=>{state.cinema='all';renderFilters();renderDay();});
load();
