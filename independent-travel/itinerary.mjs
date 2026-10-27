// Times are epoch minutes. Missing data stays unknown, never a fabricated estimate.
export function calculateTrip({departure, deadline, stops, legs}) {
  if (!Number.isInteger(departure) || !Number.isInteger(deadline) || deadline < departure) throw new Error('invalid dates');
  if (!Array.isArray(stops) || stops.length < 2 || !Array.isArray(legs) || legs.length !== stops.length - 1) throw new Error('invalid itinerary');
  let time = departure, unknown = false;
  const entries = [{name: stops[0].name, arrival: departure, departure}];
  const warnings = [];
  for (let i = 0; i < legs.length; i++) {
    const leg = legs[i], stop = stops[i + 1];
    if (!['walk','car','train','bus','flight','ferry','other'].includes(leg.mode)) throw new Error('invalid mode');
    if (leg.duration != null && (!Number.isInteger(leg.duration) || leg.duration < 0)) throw new Error('invalid duration');
    if (stop.stay != null && (!Number.isInteger(stop.stay) || stop.stay < 0)) throw new Error('invalid stay');
    if (leg.departure != null && (!Number.isInteger(leg.departure))) throw new Error('invalid leg departure');
    if (leg.departure != null && !unknown) {
      if (time > leg.departure) warnings.push({type:'missed_departure', leg:i, minutes:time-leg.departure});
      time = Math.max(time, leg.departure);
    }
    if (leg.duration == null || unknown) { unknown = true; time = null; }
    else time += leg.duration;
    const arrival = time;
    if (i < legs.length - 1) {
      if (stop.stay == null || unknown) { unknown = true; time = null; }
      else time += stop.stay;
    }
    entries.push({name:stop.name, arrival, departure:time});
  }
  if (unknown) warnings.push({type:'unknown_time'});
  else if (time > deadline) warnings.push({type:'late', minutes:time-deadline});
  return {entries, arrival:time, feasible:unknown ? null : time <= deadline && !warnings.some(x=>x.type==='missed_departure'), warnings};
}
