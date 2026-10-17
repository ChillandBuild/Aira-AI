import { Eg } from "./primitives";
import s from "./HoursRuler.module.css";

// Illustrative arrival times (hour of day) for one example day. Not real data,
// and labelled as such on the page.
const ARRIVALS = [0.6, 1.9, 6.8, 8.1, 9.2, 10.4, 11.3, 12.6, 13.4, 14.7, 15.5, 16.8, 18.1, 19.6, 20.4, 21.2, 21.9, 22.7, 23.4];
const OFFICE_START = 10;
const OFFICE_END = 19;

/** A 24-hour ruler showing enquiries arriving through an example day, many outside office hours. */
export function HoursRuler() {
  return (
    <div className={s.wrap}>
      <div className={s.ruler} role="img" aria-label="Example day: enquiries arriving across 24 hours, many outside office hours">
        <div className={s.office} style={{ left: `${(OFFICE_START / 24) * 100}%`, width: `${((OFFICE_END - OFFICE_START) / 24) * 100}%` }}>
          <span>Office hours</span>
        </div>
        {ARRIVALS.map((h) => (
          <span
            key={h}
            className={h < OFFICE_START || h >= OFFICE_END ? `${s.mark} ${s.late}` : s.mark}
            style={{ left: `${(h / 24) * 100}%` }}
          />
        ))}
        <div className={s.sweep} aria-hidden="true" />
      </div>
      <div className={s.hours} aria-hidden="true">
        <span>12 am</span><span>6 am</span><span>12 pm</span><span>6 pm</span><span>12 am</span>
      </div>
      <div className={s.legend}>
        <span><i />Enquiry during office hours</span>
        <span><i className={s.lateKey} />Enquiry after hours</span>
        <Eg>Example day, not real data</Eg>
      </div>
    </div>
  );
}
