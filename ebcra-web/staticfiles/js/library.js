/**
 * Author: Emiliano Martínez Luque
 */

(function (global) {
    'use strict';

    const REDRAW_DELAY = 120; // ms — setTimeout fallback for slider drag redraws

    // Numeric constants
    const PERCENT                 = 100; // multiplier for percentage calculations
    const DAILY_LOOKBACK_DAYS     = 30;  // window for daily variation view
    const MONTHLY_LOOKBACK_MONTHS = 12;  // window for monthly variation view
    const SLIDER_Y_MAX            = 50;  // px — top of slider sparkline range
    const SLIDER_Y_MIN            = 10;  // px — bottom of slider sparkline range
    const WIDTH_PADDING_SMALL     = 8;   // extra px subtracted on narrow viewports
    const WIDTH_PADDING           = 4;   // extra px subtracted on mid/wide viewports

    // CSS class name constants
    const CSS_ACTIVE     = 'active';
    const CSS_HANDLE     = 'handle';
    const CSS_AXIS       = 'axis';
    const CSS_SLIDER_BOX = 'slider-box';

    // ── Shared helpers ──────────────────────────────────────────────────────────

    /**
     * Compute responsive width and display flags from the current viewport.
     * Returns { width, ticks, showSliders, showToolTip, showSmallSourceNames }
     */
    function _calculateViewportWidth(conf) {
        // screen.orientation.angle is 90/270 in landscape; fall back to comparing
        // innerWidth vs innerHeight on browsers that don't support the API (older iOS Safari).
        const isLandscape = screen.orientation
            ? screen.orientation.angle % 180 !== 0
            : window.innerWidth > window.innerHeight;
        // In landscape, screen.width may still report the portrait (shorter) dimension on
        // some devices, so use innerWidth directly. In portrait, take the smaller of the two
        // to avoid an oversized chart when innerWidth has been inflated by browser zoom.
        const iWidth = isLandscape
            ? window.innerWidth
            : Math.min(window.innerWidth, window.screen.width);

        if (iWidth < conf.minWidthCutover) {
            return {
                width: iWidth - (conf.minWidthContainerMargin * 2) - WIDTH_PADDING_SMALL,
                ticks: conf.minWidthTicks,
                showSliders: false,
                showToolTip: false,
                showSmallSourceNames: true,
            };
        } else if (iWidth < conf.maxWidthCutover) {
            return {
                width: iWidth - (conf.genWidthCutoverMargin * 2) - WIDTH_PADDING,
                ticks: null,
                showSliders: true,
                showToolTip: true,
                showSmallSourceNames: false,
            };
        } else {
            return {
                width: conf.maxWidthCutover - (conf.genWidthCutoverMargin * 2) - WIDTH_PADDING,
                ticks: null,
                showSliders: true,
                showToolTip: true,
                showSmallSourceNames: false,
            };
        }
    }

    /**
     * Clip multiple data sources to their shared date range.
     * Mutates data[i].data in place.
     * Returns { earliestDay, lastDay } — the shared bounds — or null if only one source.
     */
    function _sliceDataToCommonTimeframe(data) {
        if (data.length <= 1) return null;

        let earliestDay = data[0].data[0].d;
        let lastDay = data[0].data[data[0].data.length - 1].d;

        for (let i = 1; i < data.length; i++) {
            if (earliestDay.getTime() < data[i].data[0].d.getTime()) {
                earliestDay = data[i].data[0].d;
            }
            if (lastDay.getTime() > data[i].data[data[i].data.length - 1].d.getTime()) {
                lastDay = data[i].data[data[i].data.length - 1].d;
            }
        }

        const earliestTime = earliestDay.getTime();
        const lastTime     = lastDay.getTime();
        for (let i = 0; i < data.length; i++) {
            const series = data[i].data;

            // Binary search: first index whose date >= earliestDay
            let lo = 0, hi = series.length - 1;
            while (lo < hi) {
                const mid = (lo + hi) >> 1;
                if (series[mid].d.getTime() < earliestTime) lo = mid + 1;
                else hi = mid;
            }
            const minIdx = Math.max(0, lo - 1);

            // Binary search: last index whose date <= lastDay
            lo = 0; hi = series.length - 1;
            while (lo < hi) {
                const mid = (lo + hi + 1) >> 1;
                if (series[mid].d.getTime() <= lastTime) lo = mid;
                else hi = mid - 1;
            }
            const maxIdx = Math.min(series.length - 1, lo + 1);

            data[i].data = series.slice(minIdx, maxIdx + 1);
        }

        return { earliestDay, lastDay };
    }

    /** Return true when two Date objects fall on the same UTC calendar day. */
    function _isSameDay(a, b) {
        return a.getUTCFullYear() === b.getUTCFullYear() &&
               a.getUTCMonth()   === b.getUTCMonth()    &&
               a.getUTCDate()    === b.getUTCDate();
    }

    // ── Utilities ────────────────────────────────────────────────────────────────

    const genUtils = {
        /* Format a date for string display on results */
        formatDate(d) {
            const yyyy = d.getFullYear().toString();
            const mm = (d.getMonth() + 1).toString();
            const dd = d.getDate().toString();
            return `${yyyy}-${mm[1] ? mm : '0' + mm[0]}-${dd[1] ? dd : '0' + dd[0]}`;
        },
        /* Convert a MySQL Date string to a JS Date object */
        mysqlDateToDate(s) {
            if (!s || typeof s !== 'string') return null;
            const parts = s.split('-');
            if (parts.length < 3) return null;
            return new Date(parts[0], parts[1] - 1, parts[2].substr(0, 2));
        },
        /* Format a date without the day component (YYYY-MM) */
        formatDateNoDay(d) {
            const yyyy = d.getFullYear().toString();
            const mm = (d.getMonth() + 1).toString();
            return `${yyyy}-${mm[1] ? mm : '0' + mm[0]}`;
        },
        localeFormatters: {
            es: (val) => { const n = typeof val === 'string' ? parseFloat(val) : val; return n.toLocaleString('es-AR', { maximumFractionDigits: 4 }); },
            en: (val) => { const n = typeof val === 'string' ? parseFloat(val) : val; return n.toLocaleString('en-US', { maximumFractionDigits: 4 }); },
        },
        dateLocales: {
            es: 'es-AR',
            en: 'en-US',
        },
    };

    // ── Data Loader ──────────────────────────────────────────────────────────────

    const ResponsiveChartLibraryDataLoader = {
        data: [],
        async loadAndRun(sources, milestones, postLoadFunc, jwt) {
            try {
                const headers = jwt ? { Authorization: `Bearer ${jwt}` } : {};
                const checkOk = (r, label) => {
                    if (!r.ok) throw new Error(`HTTP ${r.status} loading ${label}`);
                    return r.json();
                };
                const [milestonesData, ...sourcesData] = await Promise.all([
                    fetch(milestones, { headers }).then(r => checkOk(r, 'milestones')),
                    ...sources.map(url => fetch(url, { headers }).then(r => checkOk(r, url))),
                ]);
                this.milestones = milestonesData;
                sources.forEach((url, i) => { this.data[url] = sourcesData[i]; });
                this.postLoad(sources, postLoadFunc);
            } catch (err) {
                console.error('Failed to load chart data:', err);
            }
        },
        postLoad(sources, postLoadFunc) {
            // Pre-calculate Dates
            for (const url of sources) {
                for (const point of this.data[url]) {
                    point.d = genUtils.mysqlDateToDate(point.d);
                }
            }

            // Process Milestones — group events by date
            const milestones = [];
            let currentDate = genUtils.mysqlDateToDate(this.milestones[0].d);
            let m = { d: currentDate, p: [] };

            for (const raw of this.milestones) {
                const p = { e: raw.e, t: raw.t };
                const newDate = genUtils.mysqlDateToDate(raw.d);
                if (genUtils.formatDate(newDate) !== genUtils.formatDate(currentDate)) {
                    milestones.push(m);
                    m = { d: newDate, p: [p] };
                    currentDate = newDate;
                } else {
                    m.p.push(p);
                }
            }
            milestones.push(m);
            this.milestones = milestones;

            postLoadFunc();
        },
    };

    // ── Shared base class ────────────────────────────────────────────────────────

    class ResponsiveBase {
        /** Build a namespaced element ID string for this chart instance. */
        _id(name) { return `${name}-${this.o.id}`; }

        /** Calculate and set the properties that depend on current screen/viewport size. */
        calculateWidth() {
            const el = document.getElementById(this.o.containerId);
            const containerW = el ? el.offsetWidth : 0;
            if (containerW > 0) {
                const conf = this.conf;
                if (containerW < conf.minWidthCutover) {
                    Object.assign(this, {
                        width: containerW - (conf.minWidthContainerMargin * 2) - WIDTH_PADDING_SMALL,
                        ticks: conf.minWidthTicks,
                        showSliders: false,
                        showToolTip: false,
                        showSmallSourceNames: true,
                    });
                } else {
                    Object.assign(this, {
                        width: containerW - (conf.genWidthCutoverMargin * 2) - WIDTH_PADDING,
                        ticks: null,
                        showSliders: true,
                        showToolTip: true,
                        showSmallSourceNames: false,
                    });
                }
            } else {
                Object.assign(this, _calculateViewportWidth(this.conf));
            }
        }

        /** Clear all active classes in the view menu, then mark viewId as active. */
        _setActiveView(viewId) {
            this.viewMenu.selectAll('a').attr('class', '');
            d3.select(`#${this._id(viewId)}`).attr('class', CSS_ACTIVE);
        }

        /** Return the left margin (px) needed so the widest Y-axis tick label fits. */
        _requiredLeftMargin(yScale, defaultMargin) {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            ctx.font = '14px sans-serif';
            const maxWidth = yScale.ticks().reduce((m, t) =>
                Math.max(m, ctx.measureText(this._fmt(t)).width), 0);
            return Math.max(defaultMargin, Math.ceil(maxWidth) + 20);
        }
    }

    // ── ResponsiveChart ──────────────────────────────────────────────────────────

    class ResponsiveChart extends ResponsiveBase {
        constructor(options) {
            super();
            this.o = options;
            this.data = options.data;
            this.conf = { ...ResponsiveChart.conf, ...options.conf };
            this._defaultLeftMargin = this.conf.leftMargin;
            this._fmt = genUtils.localeFormatters[options.numberLocale] || genUtils.localeFormatters.es;
            this._dateLocale = genUtils.dateLocales[options.numberLocale] || genUtils.dateLocales.es;
            if (this.conf.addPercent) {
                const digits = this.conf.numberOfDigits ?? 2;
                const localeStr = options.numberLocale === 'en' ? 'en-US' : 'es-AR';
                this._fmt = (val) => {
                    const n = typeof val === 'string' ? parseFloat(val) : val;
                    return n.toLocaleString(localeStr, { minimumFractionDigits: digits, maximumFractionDigits: digits }) + '%';
                };
            }
            if (!this.conf.views.some(v => v.id === 'allTime')) {
                this.conf.views = [...this.conf.views, { view: null, text: this.conf.lang.allTimeText || 'All Records', id: 'allTime' }];
            }
            this.init();
        }

        /* Internal Variables

         this.conf                      — The merged configuration (ResponsiveChart.conf overridden by options.conf)

         // Screen Size Data
         this.width: INT                — Current width of chart, calculated from screen width and conf parameters
         this.ticks: INT                — Number of ticks on the time axis, calculated from screen width
         this.showSliders: BOOL         — Whether to show the slider handles (false on mobile)
         this.showToolTip: BOOL         — Whether to show the hover tooltip (false on mobile)
         this.showSmallSourceNames: BOOL — Whether to show the compact source-name labels (true on mobile)

         // Data and currently displayed info
         this.data [{
             data: [{v, d}]             — Full data array for this series
             currentData: [{v, d}]      — Slice of data for the active view (threeMonths / oneYear / …)
             currentDisplayData: [{v, d}] — Slice of currentData visible between the slider handles

             resultsDiv: div            — The div inside the results pane for this series

             allTimeIndex, threeMonthsIndex, oneYearIndex, fiveYearsIndex: INT — pre-computed slice indices
         }]  — one entry per series

         this.currentView: STRING       — Active view key: "threeMonths"|"oneYear"|"fiveYears"|"allTime"
         this.timeScale                 — D3 time scale for the current display data
         this.yScale                    — D3 linear scale for the current display data
         this.milestonesShown: BOOL     — Whether milestone lines are currently visible

         // D3 Elements
         this.container                 — div#{options.containerId}  — outer wrapper
         this.graphContainer            — div#graph-container-{id}   — holds SVG + slider + results
         this.graphSvg                  — svg#graph-svg-{id}         — the chart SVG

         this.axisDrawn: BOOL           — Whether axis elements have been created yet
         this.timeAxis                  — svg:g#time-axis{id}        — horizontal time axis
         this.numAxis                   — svg:g#num-axis{id}         — vertical value axis

         this.sliderContainer           — div#slider-container-{id}
         this.sliderSvg                 — svg#slider-svg-{id}
         this.sliderResultsContainer    — div#results-container-{id}
         this.sliderBox                 — svg:rect#sliderBox-{id}    — the highlighted range box
         this.handle1                   — svg:rect#handle1-{id}      — left drag handle
         this.handle2                   — svg:rect#handle2-{id}      — right drag handle
         this.currentHandle1Pos         — left handle position as a fraction of width (used on resize)
         this.currentHandle2Pos         — right handle position as a fraction of width

         this.viewMenu                  — div#views-menu-{id}        — time-range button bar
         this.mouseOverRect             — svg:rect  — transparent hit area for mouse events
         this.toolTipContainer          — svg:g     — tooltip group
         this.toolTipBackground         — svg:rect  — tooltip background rect
         this.toolTipDate               — svg:text  — date label inside tooltip
         this.toolTipTexts              — [svg:text] — one value label per series

         this.milestonesLines           — svg:g     — group containing all milestone vertical lines
         this.milestonesContainer       — svg:g     — group containing the milestone detail panel
         this.milestonesBackground      — svg:rect  — background rect of the milestone panel
         this.milestonesDate            — svg:text  — date label in the milestone panel
         this.milestonesText            — svg:text  — event text lines in the milestone panel
         this.milestonesMenu            — div#milestones-menu-{id}   — "Show Events" toggle container
         this.milestonesButton          — a         — "Show Events" toggle anchor
         */

        /* Initialize the chart: process data, build DOM, draw everything */
        init() {
            this.postLoad();
            this.calculateWidth();
            this.container = d3.select(`#${this.o.containerId}`);
            this.generateViewsMenu();
            this.generateBasicElements();
            this.calculateScales(0, this.width);
            this.drawBackgroundBands();
            this.drawLines();
            this.drawAxis();
            if (this.showSliders) {
                this.generateSliders();
                if (this.conf.showResultsPane) this.showResults(0, this.width);
            }
            if (this.showToolTip) {
                this.addMouseOverRect();
                this.addMilestones();
                this.addToolTip();
            }
        }

        /* Align data sources to a common timeframe, fill date gaps, then calculate view indexes */
        postLoad() {
            if (this.data.length > 1) {
                const bounds = _sliceDataToCommonTimeframe(this.data);
                if (bounds) {
                    const { earliestDay, lastDay } = bounds;
                    // Gap-fill each series so all share identical calendar days
                    for (let i = 0; i < this.data.length; i++) {
                        const series = this.data[i].data;
                        const tmp = [];
                        let m = 0;
                        const currentDay = new Date(earliestDay);
                        while (currentDay.getTime() <= lastDay.getTime()) {
                            // Advance m past any entries that predate currentDay.
                            // This handles the lookback element included by _sliceDataToCommonTimeframe
                            // (minIdx = lo - 1) for the earlier-starting series.
                            while (m < series.length - 1 && series[m].d.getTime() < currentDay.getTime()) {
                                m++;
                            }
                            if (_isSameDay(currentDay, series[m].d)) {
                                tmp.push(series[m]);
                                m++;
                                if (m === series.length) m--;
                            } else {
                                if (series[m].dv) {
                                    tmp.push({ d: new Date(currentDay), v: series[m].v, dv: series[m].dv });
                                } else {
                                    tmp.push({ d: new Date(currentDay), v: series[m].v });
                                }
                            }
                            currentDay.setUTCDate(currentDay.getUTCDate() + 1);
                        }
                        this.data[i].data = tmp;
                    }
                }
            }

            if (!this.o.initialView) this.o.initialView = this.conf.defaultInitialView;
            this.calculateTimeViewIndexes();
            this.o.postLoad?.();
        }

        /**
         * Calculate the data-array indexes that correspond to each time-range view.
         * Populates data[i].allTimeIndex, data[i].threeMonthsIndex, etc.
         */
        calculateTimeViewIndexes() {
            const searchIndexByDate = (dataIndex, targ) => {
                const arr = this.data[dataIndex].data;
                const targTime = targ.getTime();
                let lo = 0, hi = arr.length - 1;
                while (lo < hi) {
                    const mid = (lo + hi + 1) >> 1;
                    if (arr[mid].d.getTime() <= targTime) lo = mid;
                    else hi = mid - 1;
                }
                return lo;
            };

            for (let i = 0; i < this.data.length; i++) {
                const lastIndex = this.data[i].data.length - 1;
                for (const viewConf of this.conf.views) {
                    if (viewConf.view === null) {
                        this.data[i][`${viewConf.id}Index`] = 0;
                    } else {
                        const targ = new Date(this.data[i].data[lastIndex].d);
                        targ.setUTCDate(targ.getUTCDate()         - (viewConf.view[0] || 0));
                        targ.setUTCMonth(targ.getUTCMonth()       - (viewConf.view[1] || 0));
                        targ.setUTCFullYear(targ.getUTCFullYear() - (viewConf.view[2] || 0));
                        this.data[i][`${viewConf.id}Index`] = searchIndexByDate(i, targ);
                    }
                }
                if (this.o.initialView) {
                    this.currentView = this.o.initialView;
                    this.data[i].currentData = this.data[i].data.slice(
                        this.data[i][`${this.o.initialView}Index`]
                    );
                    this.data[i].currentDisplayData = this.data[i].data;
                }
            }
        }

        /* Generate the basic container DOM and SVG elements */
        generateBasicElements() {
            this.graphContainer = this.container.append('div').attr('id', this._id('graph-container'));
            this.graphSvg = this.graphContainer.append('svg')
                .attr('id', this._id('graph-svg'))
                .attr('height', this.conf.height)
                .attr('width', this.width);

            if (this.showToolTip) {
                this.milestonesMenu = this.graphContainer.append('div')
                    .attr('id', this._id('milestones-menu'))
                    .attr('class', 'milestones-menu');
                if (this.milestoneNavLabel) {
                    this.milestonesMenu.append('span')
                        .attr('class', 'milestone-nav-label')
                        .text(this.milestoneNavLabel);
                }
                this.milestonesButton = this.milestonesMenu.append('a')
                    .attr('href', '#')
                    .html(this.conf.lang.showEvents);

                if (this.milestonesShown) this.milestonesButton.attr('class', CSS_ACTIVE);

                this.milestonesButton.on('click', (event) => {
                    event.preventDefault();
                    if (this.milestonesShown) {
                        this.milestonesLines.attr('display', 'none');
                        this.milestonesShown = false;
                        this.milestonesButton.attr('class', '');
                    } else {
                        this.milestonesLines.attr('display', 'inline');
                        this.milestonesShown = true;
                        this.milestonesButton.attr('class', CSS_ACTIVE);
                    }
                });
            }

            if (this.showSmallSourceNames && this.data.length > 1) {
                const sourceNamesContainer = this.graphContainer.append('div').attr('class', 'source-names');
                for (const { stroke, name } of this.data) {
                    sourceNamesContainer.append('div').attr('style', `color:${stroke};`).text(name);
                }
            }
        }

        /* Generate the time-range view button bar */
        generateViewsMenu() {
            this.viewMenu = this.container.append('div')
                .attr('id', this._id('views-menu'))
                .attr('class', 'view-menu');

            for (const viewConf of this.conf.views) {
                const startIndexKey = `${viewConf.id}Index`;
                const currentViewId = viewConf.id;
                const view = this.viewMenu.append('a')
                    .attr('href', '#')
                    .html(viewConf.text)
                    .attr('id', this._id(viewConf.id));
                if (this.currentView === viewConf.id) view.attr('class', CSS_ACTIVE);
                view.on('click', (event) => {
                    event.preventDefault();
                    if (this.currentView !== currentViewId) {
                        for (const d of this.data) {
                            d.currentData = d.data.slice(d[startIndexKey]);
                        }
                        this.currentView = currentViewId;
                        this.changeView();
                    }
                });
            }
        }

        /**
         * Convert pixel handle positions to data-array indices for a series.
         * @param {Object} series   — a data series with a `currentData` array
         * @param {number} minPx    — left handle pixel position
         * @param {number} maxPx    — right handle pixel position (handle x + handle width)
         * @returns {{ arrMin: number, arrMax: number }}
         */
        _dataIndices(series, minPx, maxPx) {
            const ratio = series.currentData.length / this.width;
            return {
                arrMin: Math.round(minPx * ratio),
                arrMax: Math.round(maxPx * ratio) - 1,
            };
        }

        /**
         * Calculate Y and time scales for lines and axes.
         * @param min {Int} Current pixel position of the left slider handle
         * @param max {Int} Current pixel position of the right slider handle + its width
         */
        calculateScales(min, max) {
            for (const series of this.data) {
                const { arrMin, arrMax } = this._dataIndices(series, min, max);
                series.currentDisplayData = series.currentData.slice(arrMin, arrMax + 1);
            }

            const allDataPoints = this.data.flatMap(d => d.currentDisplayData);
            const [minDate, maxDate] = d3.extent(allDataPoints, d => d.d);
            if (!minDate) { console.warn('ResponsiveChart: no data points to render'); return; }
            const [yMin, yMax] = d3.extent(allDataPoints, d => d.v);
            const yPad = yMin === yMax ? (Math.abs(yMin) * 0.1 || 1) : 0;
            this.yScale = d3.scaleLinear().domain([yMin - yPad, yMax + yPad]).range([this.conf.height - this.conf.bottomMargin, 0]);
            this.conf.leftMargin = this._requiredLeftMargin(this.yScale, this.conf.leftMargin);
            this.timeScale = d3.scaleTime().domain([minDate, maxDate]).range([this.conf.leftMargin, this.width - 1]);
        }

        /** Draw or redraw all series lines on the chart SVG */
        drawLines() {
            const { timeScale, yScale } = this;
            const line = d3.line()
                .x(d => timeScale(d.d))
                .y(d => yScale(d.v));

            const paths = this.graphSvg.selectAll('path.series-line')
                .data(this.data, d => d.id);

            paths.enter()
                .append('path')
                .attr('class', 'series-line')
                .attr('id', d => `line-${this.o.containerId}-${d.id}`)
                .attr('stroke', d => d.stroke)
                .attr('stroke-width', 1.05)
                .attr('fill', 'none')
                .merge(paths)
                .attr('d', d => line(d.currentDisplayData));
        }

        drawBackgroundBands() {
            const [minDate, maxDate] = this.timeScale.domain();
            const chartBottom = this.conf.height - this.conf.bottomMargin;
            const leftMargin = this.conf.leftMargin;
            const rightEdge = this.width - 1;
            const color = this.conf.alternateBandColor;

            const ticks = this.ticks ? this.timeScale.ticks(this.ticks) : this.timeScale.ticks();
            const boundaries = [minDate, ...ticks, maxDate];
            const autoBands = [];
            for (let i = 0; i < boundaries.length - 1; i++) {
                if (i % 2 === 0) {
                    autoBands.push({ start: boundaries[i], end: boundaries[i + 1] });
                }
            }

            let altG = this.graphSvg.select('g.chart-alternating-bands');
            if (altG.empty()) {
                altG = this.graphSvg.insert('g', ':first-child')
                    .attr('class', 'chart-alternating-bands');
            }

            const rects = altG.selectAll('rect').data(autoBands);
            rects.enter().append('rect').merge(rects)
                .attr('x', d => Math.max(leftMargin, this.timeScale(d.start)))
                .attr('y', 0)
                .attr('width', d => Math.max(0,
                    Math.min(rightEdge, this.timeScale(d.end)) -
                    Math.max(leftMargin, this.timeScale(d.start))))
                .attr('height', chartBottom)
                .attr('fill', color);
            rects.exit().remove();

            const bands = this.conf.backgroundBands || [];
            const groups = this.graphSvg.selectAll('g.background-band')
                .data(bands);

            const entered = groups.enter()
                .append('g')
                .attr('class', 'background-band')
                .attr('pointer-events', 'none');
            entered.append('rect');
            entered.append('text');

            const merged = entered.merge(groups);

            merged.each((d, i, nodes) => {
                const x1 = Math.max(leftMargin, this.timeScale(new Date(d.start)));
                const x2 = Math.min(rightEdge, this.timeScale(new Date(d.end)));
                const bandWidth = Math.max(0, x2 - x1);
                const g = d3.select(nodes[i]);

                g.select('rect')
                    .attr('x', x1)
                    .attr('y', 0)
                    .attr('width', bandWidth)
                    .attr('height', chartBottom)
                    .attr('fill', d.color || 'rgba(200,200,200,0.2)');

                const labelText = d.label || '';
                const labelVisible = bandWidth > 20 && labelText;
                g.select('text')
                    .attr('x', x1 + bandWidth / 2)
                    .attr('y', 14)
                    .attr('text-anchor', 'middle')
                    .attr('fill', d.labelColor || 'rgba(0,0,0,0.35)')
                    .attr('font-size', '10px')
                    .attr('display', labelVisible ? null : 'none')
                    .text(labelText);
            });

            groups.exit().remove();
        }

        _tickFormat(d) {
            const loc = this._dateLocale;
            if (d3.timeYear(d) < d) {
                if (d3.timeMonth(d) < d) return d.toLocaleString(loc, { month: 'short', day: 'numeric' });
                return d.toLocaleString(loc, { month: 'short' });
            }
            return d.toLocaleString(loc, { year: 'numeric' });
        }

        /** Draw or redraw the time (X) and value (Y) axes */
        drawAxis() {
            const { timeScale, yScale } = this;

            const timeAxis = d3.axisBottom(timeScale)
                .tickSize(-(this.conf.height - this.conf.bottomMargin))
                .tickPadding(10)
                .tickFormat(d => this._tickFormat(d));
            if (this.ticks) timeAxis.ticks(this.ticks);
            const yAxis = d3.axisLeft(yScale)
                .tickSize(-(this.width - this.conf.leftMargin - 1))
                .tickPadding(10)
                .tickFormat(d => this._fmt(d));

            if (this.axisDrawn) {
                this.timeAxis.call(timeAxis);
                this.numAxis
                    .attr('transform', `translate(${this.conf.leftMargin},0)`)
                    .call(yAxis);
            } else {
                this.timeAxis = this.graphSvg.append('g')
                    .attr('id', this._id('time-axis'))
                    .attr('class', CSS_AXIS)
                    .attr('transform', `translate(0,${this.conf.height - this.conf.bottomMargin})`)
                    .call(timeAxis);
                this.numAxis = this.graphSvg.append('g')
                    .attr('id', this._id('num-axis'))
                    .attr('class', CSS_AXIS)
                    .attr('transform', `translate(${this.conf.leftMargin},0)`)
                    .call(yAxis);
                this.axisDrawn = true;
            }
        }

        /** Generate the full slider (static elements + drag handles + events) */
        generateSliders() {
            this.generateSliderStaticElements();
            this.generateSliderHandlers();
            this.addHandlerEvents();
        }

        /* Generate the slider container, mini-chart SVG, and results div */
        generateSliderStaticElements() {
            this.sliderContainer = this.graphContainer.append('div').attr('id', this._id('slider-container'));
            this.sliderSvg = this.sliderContainer.append('svg')
                .attr('id', this._id('slider-svg'))
                .attr('width', this.width)
                .attr('height', this.conf.sliderContainerHeight)
                .style('overflow', 'visible');
            this.sliderResultsContainer = this.graphContainer.append('div')
                .attr('id', this._id('results-container'))
                .attr('class', 'slider-results');

            const allDataPoints = this.data.flatMap(d => d.currentData);
            const timeExtentSmall = d3.extent(allDataPoints, d => d.d);
            const timeScaleSmall = d3.scaleTime().domain(timeExtentSmall).range([0, this.width]);
            const yExtentSmall = d3.extent(allDataPoints, d => d.v);
            const yScaleSmall = d3.scaleLinear().domain(yExtentSmall).range([SLIDER_Y_MAX, SLIDER_Y_MIN]);

            const clipId = this._id('slider-clip');
            this.sliderSvg.append('defs').append('clipPath')
                .attr('id', clipId)
                .append('rect')
                    .attr('x', this.conf.sliderHandleWidth)
                    .attr('y', 0)
                    .attr('width', this.width - this.conf.sliderHandleWidth * 2)
                    .attr('height', this.conf.sliderContainerHeight);

            const lineSmall = d3.line()
                .x(d => timeScaleSmall(d.d))
                .y(d => yScaleSmall(d.v));
            for (const series of this.data) {
                this.sliderSvg.append('path')
                    .attr('id', `line-${this.o.id}-slider-${series.id}`)
                    .attr('d', lineSmall(series.currentData))
                    .attr('stroke', series.stroke)
                    .attr('fill', 'none')
                    .attr('clip-path', `url(#${clipId})`);
            }

            if (this.conf.showResultsPane) {
                for (const series of this.data) {
                    series.resultsDiv = this.sliderResultsContainer.append('div').style('background-color', series.stroke);
                }
            }
        }

        /* Build a grabber-style drag handle: a <g> with a transparent hit area,
           a rounded thumb rect, and three horizontal grip lines. */
        _appendHandle(xPos, handleId) {
            const hw = this.conf.sliderHandleWidth;
            const hh = this.conf.sliderContainerHeight;
            const thumbH = 36;
            const thumbY = (hh - thumbH) / 2;
            const cy = hh / 2;
            const g = this.sliderSvg.append('g')
                .attr('id', this._id(handleId))
                .attr('class', CSS_HANDLE)
                .attr('x', xPos)
                .attr('transform', `translate(${xPos},0)`);
            g.append('rect').attr('class', 'hit-area')
                .attr('x', 0).attr('y', 0).attr('width', hw).attr('height', hh);
            g.append('rect').attr('class', 'thumb')
                .attr('x', 0).attr('y', thumbY).attr('width', hw).attr('height', thumbH).attr('rx', 3);
            for (const dy of [-5, 0, 5]) {
                g.append('line').attr('x1', 2).attr('x2', hw - 2)
                    .attr('y1', cy + dy).attr('y2', cy + dy);
            }
            return g;
        }

        /* Generate the two drag-handle elements for the slider */
        generateSliderHandlers() {
            if (this.currentHandle1Pos) {
                const minRaw = Math.round(this.currentHandle1Pos * this.width);
                const maxRaw = Math.round(this.currentHandle2Pos * this.width);
                const boxWidth = maxRaw - minRaw;
                this.sliderBox = this.sliderSvg.append('rect')
                    .attr('id', this._id('sliderBox'))
                    .attr('x', minRaw).attr('width', boxWidth)
                    .attr('y', (this.conf.sliderContainerHeight - this.conf.sliderBoxHeight) / 2)
                    .attr('height', this.conf.sliderBoxHeight)
                    .attr('rx', 4)
                    .attr('class', CSS_SLIDER_BOX);
                this.handle1 = this._appendHandle(minRaw, 'handle1');
                this.handle2 = this._appendHandle(maxRaw, 'handle2');
            } else {
                this.sliderBox = this.sliderSvg.append('rect')
                    .attr('id', this._id('sliderBox'))
                    .attr('x', this.conf.sliderHandleWidth)
                    .attr('y', (this.conf.sliderContainerHeight - this.conf.sliderBoxHeight) / 2)
                    .attr('width', this.width - (this.conf.sliderHandleWidth * 2))
                    .attr('height', this.conf.sliderBoxHeight)
                    .attr('rx', 4)
                    .attr('class', CSS_SLIDER_BOX);
                this.handle1 = this._appendHandle(0, 'handle1');
                this.handle2 = this._appendHandle(this.width - this.conf.sliderHandleWidth, 'handle2');
            }
        }

        /* Attach drag events to both slider handles */
        addHandlerEvents() {
            const redrawBox = () => {
                const a = +this.handle1.attr('x') + this.conf.sliderHandleWidth;
                const b = +this.handle2.attr('x');
                this.sliderBox.attr('x', a).attr('width', b - a);
            };

            let redrawTimer;

            const attachDrag = (handle, clampPosition) => {
                handle.call(d3.drag()
                    .on('start', () => {
                        handle.attr('class', `${CSS_HANDLE} ${CSS_ACTIVE}`);
                        this.viewMenu.selectAll('a').attr('class', '');
                        this.currentView = null;
                        if (this.milestoneNavLabel) {
                            this.milestoneNavLabel = null;
                            if (this.milestonesMenu) this.milestonesMenu.select('.milestone-nav-label').remove();
                        }
                    })
                    .on('drag', (event) => {
                        const positionHandle = () => {
                            const newX = clampPosition(event.x);
                            handle.attr('x', newX).attr('transform', `translate(${newX},0)`);
                            redrawBox();
                        };
                        if (window.requestAnimationFrame) {
                            window.requestAnimationFrame(() => { positionHandle(); this.redrawGraph(); });
                        } else {
                            positionHandle();
                            clearTimeout(redrawTimer);
                            redrawTimer = setTimeout(() => { this.redrawGraph(); }, REDRAW_DELAY);
                        }
                    })
                    .on('end', () => { handle.attr('class', CSS_HANDLE); })
                );
            };

            attachDrag(this.handle1, (x) => {
                const h2x = +this.handle2.attr('x');
                if (x > h2x - this.conf.sliderHandleWidth) return h2x - this.conf.sliderHandleWidth;
                if (x <= this.conf.sliderHandleWidth) return 0;
                return x;
            });

            attachDrag(this.handle2, (x) => {
                const h1x = +this.handle1.attr('x');
                if (x < h1x + this.conf.sliderHandleWidth) return h1x + this.conf.sliderHandleWidth;
                if (x >= this.width - this.conf.sliderHandleWidth) return this.width - this.conf.sliderHandleWidth;
                return x;
            });
        }

        /* Populate the results pane with start value, end value, and % change for the current range */
        showResults(min, max) {
            for (const series of this.data) {
                const { arrMin, arrMax } = this._dataIndices(series, min, max);
                const dateMin = series.currentData[arrMin].d;
                const dateMax = series.currentData[arrMax].d;
                const percent = ((series.currentData[arrMax].v - series.currentData[arrMin].v) / series.currentData[arrMin].v) * PERCENT;
                const valMin = series.currentData[arrMin].dv ?? series.currentData[arrMin].v;
                const valMax = series.currentData[arrMax].dv ?? series.currentData[arrMax].v;
                series.resultsDiv.html(
                    `<table><tr><td class='text'>${series.name}</td>` +
                    `<td>${genUtils.formatDate(dateMin)}: ${this._fmt(valMin)}</td>` +
                    `<td>${genUtils.formatDate(dateMax)}: ${this._fmt(valMax)}</td>` +
                    `<td> <span class='text'>Var:</span> ${percent.toFixed(2)}%</td></tr></table>`
                );
            }
        }

        addMouseOverRect() {
            this.mouseOverRect = this.graphSvg.append('svg:rect')
                .attr('x', this.conf.leftMargin)
                .attr('width', this.width)
                .attr('height', this.conf.height)
                .attr('fill', 'none')
                .attr('pointer-events', 'all');
        }

        addToolTip() {
            this.toolTipContainer = this.graphSvg.append('g')
                .attr('transform', `translate(${this.conf.leftMargin + this.conf.toolTipContainerXMargin},${this.conf.toolTipContainerTopMargin})`);

            const toolTipContainerBGHeight = this.conf.toolTipBGTopPadding + (this.conf.toolTipTextsSize * this.data.length) + this.conf.toolTipBGBottomPadding;
            this.toolTipBGWidth = this.conf.toolTipContainerBGWidth;
            this.toolTipBackground = this.toolTipContainer.append('rect')
                .attr('x', 0).attr('y', 0)
                .attr('height', toolTipContainerBGHeight)
                .attr('width', this.toolTipBGWidth)
                .attr('rx', 6).attr('ry', 6)
                .attr('fill', 'none');

            this.toolTipDate = this.toolTipContainer.append('text')
                .attr('class', 'tooltip-date')
                .attr('y', this.conf.toolTipBGTopPadding)
                .attr('x', this.conf.toolTipLeftPadding);

            this.toolTipTexts = this.data.map((series, i) =>
                this.toolTipContainer.append('text')
                    .attr('x', this.conf.toolTipLeftPadding)
                    .attr('y', ((i + 1) * this.conf.toolTipTextsSize) + this.conf.toolTipBGTopPadding)
                    .attr('class', 'tooltip-text')
                    .attr('fill', series.stroke)
            );

            // Grow the box at init to fit the widest text that will ever appear.
            {
                const padding = this.conf.toolTipLeftPadding * 2;

                const worstCaseValues = this.data.map(series => {
                    const maxAbsVal = series.data.reduce((best, pt) => {
                        const v = pt.dv ?? pt.v;
                        return Math.abs(v) > Math.abs(best) ? v : best;
                    }, 0);
                    return `${series.name}: ${this._fmt(maxAbsVal)}`;
                });

                const measureText = (text, cssClass) => {
                    const tmp = this.toolTipContainer.append('text')
                        .attr('class', cssClass)
                        .style('visibility', 'hidden')
                        .text(text);
                    const len = tmp.node().getComputedTextLength();
                    tmp.remove();
                    return len;
                };

                const maxMeasured = Math.max(
                    measureText('2020-12-31', 'tooltip-date'),
                    ...worstCaseValues.map(s => measureText(s, 'tooltip-text'))
                );

                if (maxMeasured > 0) {
                    const needed = Math.ceil(maxMeasured) + padding;
                    if (needed > this.toolTipBGWidth) {
                        this.toolTipBGWidth = needed;
                        this.toolTipBackground.attr('width', this.toolTipBGWidth);
                    }
                }
            }

            const bisectDate = d3.bisector(d => d.d).left;

            this.mouseOverRect.on('mousemove', (event) => {
                const actualX = d3.pointer(event)[0];
                const x0 = this.timeScale.invert(actualX);
                const realWidth = this.width - this.conf.leftMargin;

                if (actualX < this.width / 2) {
                    this.toolTipContainer.attr('transform', `translate(${this.width - this.toolTipBGWidth - this.conf.toolTipContainerXMargin},${this.conf.toolTipContainerTopMargin})`);
                } else {
                    this.toolTipContainer.attr('transform', `translate(${this.conf.leftMargin + this.conf.toolTipContainerXMargin},${this.conf.toolTipContainerTopMargin})`);
                }

                this.toolTipBackground.attr('fill', this.conf.panelsBGColor);

                this.data.forEach((series, i) => {
                    const data = series.currentDisplayData;
                    const bisectIdx = bisectDate(data, x0, 1);
                    if (bisectIdx === 0 || bisectIdx >= data.length) return;
                    const d0 = data[bisectIdx - 1];
                    const d1 = data[bisectIdx];
                    const d = x0 - d0.d > d1.d - x0 ? d1 : d0;
                    if (i === 0) this.toolTipDate.text(genUtils.formatDate(d.d));
                    const val = d.dv ?? d.v;
                    this.toolTipTexts[i].text(`${series.name}: ${this._fmt(val)}`);
                });
            });

            this.mouseOverRect.on('mouseout', () => {
                this.toolTipBackground.attr('fill', 'none');
                this.toolTipDate.text('');
                for (const t of this.toolTipTexts) t.text('');
            });
        }

        addMilestones() {
            const milestones = this.o.milestones;
            this.milestonesLines = this.graphSvg.append('g');

            for (const milestone of milestones) {
                const x = this.timeScale(milestone.d);
                if (x > this.conf.leftMargin) {
                    const g = this.milestonesLines.append('g').attr('class', 'milestone-lines');
                    g.append('line')
                        .attr('x1', x).attr('y1', 0)
                        .attr('x2', x).attr('y2', this.conf.height - this.conf.bottomMargin)
                        .attr('stroke-width', 1);
                    const half = Math.round(this.conf.milestonesRectWidth / 2);
                    const rect = g.append('polygon')
                        .attr('points', `${x - half},0 ${x + half},0 ${x},${this.conf.milestonesRectHeight}`)
                        .style('cursor', 'pointer')
                        .style('fill', '#066688')
                        .style('stroke', '#000000')
                        .style('stroke-width', '1px');

                    const texts = this.o.milestonesTextFunc(milestone.p);
                    const dat = milestone.d;

                    rect.on('mouseover', () => {
                        this._showMilestoneBox(texts, dat, milestone.p);
                    });

                    rect.on('mouseout', () => {
                        if (this.pinnedMilestoneData) {
                            const { texts: pt, dat: pd, p: pp } = this.pinnedMilestoneData;
                            this._showMilestoneBox(pt, pd, pp);
                        } else {
                            this._hideMilestoneBox();
                        }
                    });

                    rect.on('click', (event) => {
                        event.stopPropagation();
                        const alreadyPinned = this.pinnedMilestoneData
                            && this.pinnedMilestoneData.datTs === dat.getTime();
                        if (alreadyPinned) {
                            this.pinnedMilestoneData = null;
                            this._hideMilestoneBox();
                        } else {
                            this.pinnedMilestoneData = { texts, dat, datTs: dat.getTime(), p: milestone.p };
                            this._showMilestoneBox(texts, dat, milestone.p);
                        }
                    });
                }
            }

            this.milestonesContainer = this.graphSvg.append('g');
            this.milestonesBackground = this.milestonesContainer.append('rect')
                .attr('x', 0).attr('y', 0)
                .attr('height', '0')
                .attr('width', this.conf.milestonesBGWidth)
                .attr('rx', 6).attr('ry', 6)
                .attr('fill', 'none');
            this.milestonesDate = this.milestonesContainer.append('text')
                .attr('class', 'milestones-date')
                .attr('y', this.conf.milestonesTopPadding)
                .attr('x', this.conf.milestonesLeftPadding);
            this.milestonesText = this.milestonesContainer.append('text')
                .attr('class', 'milestones-text')
                .attr('y', this.conf.milestonesTopPadding)
                .attr('x', this.conf.milestonesLeftPadding);

            this.graphSvg.on('click.milestone-unpin', () => {
                if (this.pinnedMilestoneData) {
                    this.pinnedMilestoneData = null;
                    this._hideMilestoneBox();
                }
            });

            if (!this.milestonesShown) {
                this.milestonesLines.attr('display', 'none');
            }
        }

        _showMilestoneBox(texts, dat, p) {
            this.milestonesText.selectAll('tspan').remove();
            const milestonesBGHeight = this.conf.milestonesTopPadding + 2
                + (texts.length * this.conf.milestonesTextSize)
                + this.conf.milestonesBottomPadding;
            this.milestonesBackground.attr('fill', this.conf.panelsBGColor).attr('height', milestonesBGHeight);
            const milestonesContainerY = this.conf.height - this.conf.bottomMargin
                - milestonesBGHeight - this.conf.milestonesContainerBottomMargin;
            const milestonesContainerX = this.conf.leftMargin + this.conf.toolTipContainerXMargin;
            this.milestonesContainer.attr('transform', `translate(${milestonesContainerX},${milestonesContainerY})`);
            for (let ti = 0; ti < texts.length; ti++) {
                const entry = p[ti];
                const isClickable = entry.t === 'bcra' || entry.t === 'pres'
                    || entry.t === 'econ' || entry.t === 'fina' || entry.t === 'trea';
                const span = this.milestonesText.append('tspan')
                    .text(texts[ti])
                    .attr('y', this.conf.milestonesTopPadding + 2 + ((ti + 1) * this.conf.milestonesTextSize))
                    .attr('x', this.conf.milestonesLeftPadding);
                if (isClickable) {
                    span.style('cursor', 'pointer').style('text-decoration', 'underline');
                    span.on('click', (event) => {
                        event.stopPropagation();
                        this._navigateToMilestoneEntry(dat, entry.t, texts[ti]);
                    });
                }
            }
            this.milestonesDate.text(genUtils.formatDate(dat));
        }

        _hideMilestoneBox() {
            this.milestonesText.text('');
            this.milestonesDate.text('');
            this.milestonesBackground.attr('fill', 'none');
        }

        /**
         * Redraw graph elements (lines, axes, results, milestones).
         * Called when a slider handle is moved or when the window is resized.
         */
        redrawGraph() {
            let min, max;
            if (this.handle1) {
                min = parseInt(this.handle1.attr('x'), 10);
                max = parseInt(this.handle2.attr('x'), 10) + this.conf.sliderHandleWidth;
            } else {
                min = 0;
                max = this.width;
            }
            this.currentHandle1Pos = min / this.width;
            this.currentHandle2Pos = (max - this.conf.sliderHandleWidth) / this.width;
            this.calculateScales(min, max);
            this.drawBackgroundBands();
            this.drawLines();
            this.drawAxis();
            if (this.showSliders && this.conf.showResultsPane) this.showResults(min, max);
            if (this.showToolTip) {
                this.cleanUpToolTipAndMilestones();
                this.addMouseOverRect();
                this.addMilestones();
                this.addToolTip();
            }
        }

        /* Null out tooltip and milestone references so they can be re-created on the next redraw */
        cleanUpToolTipAndMilestones() {
            if (this.toolTipContainer) {
                this.mouseOverRect = null;
                this.toolTipDate = null;
                this.toolTipTexts = null;
                this.toolTipBackground = null;
                this.toolTipContainer = null;
            }
            if (this.milestonesContainer) {
                this.pinnedMilestoneData = null;
                this.milestonesLines.remove();
                this.milestonesLines = null;
                this.milestonesBackground = null;
                this.milestonesDate = null;
                this.milestonesText = null;
                this.milestonesContainer.remove();
                this.milestonesContainer = null;
            }
        }

        /** Remove all DOM elements and null out all references to assist garbage collection */
        cleanUp() {
            if (this.sliderContainer) {
                this.handle1 = null;
                this.handle2 = null;
                this.sliderBox = null;
                this.sliderSvg = null;
                if (this.conf.showResultsPane) {
                    for (const series of this.data) series.resultsDiv = null;
                }
                this.sliderResultsContainer = null;
                this.sliderContainer.remove();
                this.sliderContainer = null;
            }
            this.timeAxis = null;
            this.numAxis = null;
            this.graphSvg = null;
            if (this.graphContainer) this.graphContainer.remove();
            this.graphContainer = null;
            this.axisDrawn = false;
            if (this.milestonesMenu) {
                this.milestonesButton = null;
                this.milestonesMenu.remove();
                this.milestonesMenu = null;
            }
        }

        /** Resize the chart in response to a window resize event */
        resize() {
            this.cleanUp();
            this.calculateWidth();
            this.generateBasicElements();
            if (this.showSliders) this.generateSliders();
            this.redrawGraph();
        }

        /** Rebuild all DOM and SVG elements, honouring currentHandle1Pos/currentHandle2Pos */
        _fullRedraw() {
            this.cleanUpToolTipAndMilestones();
            this.cleanUp();
            this.mouseOverRect = null;
            this.generateBasicElements();
            this.calculateScales(0, this.width);
            this.drawBackgroundBands();
            this.drawLines();
            this.drawAxis();
            if (this.showSliders) {
                this.generateSliders();
                if (this.conf.showResultsPane) this.showResults(0, this.width);
            }
            if (this.showToolTip) {
                this.addMouseOverRect();
                this.addMilestones();
                this.addToolTip();
            }
            this._setActiveView(this.currentView);
        }

        /** Zoom chart to show the date range [startDate, endDate] using allTime data */
        _navigateToDateRange(startDate, endDate) {
            for (const d of this.data) {
                d.currentData = d.data.slice(d.allTimeIndex);
            }
            this.currentView = null;

            const arr = this.data[0].currentData;
            const startTime = startDate.getTime();
            const endTime   = endDate.getTime();

            let lo = 0, hi = arr.length - 1;
            while (lo < hi) {
                const mid = (lo + hi + 1) >> 1;
                if (arr[mid].d.getTime() <= startTime) lo = mid; else hi = mid - 1;
            }
            const startIdx = lo;

            lo = 0; hi = arr.length - 1;
            while (lo < hi) {
                const mid = (lo + hi + 1) >> 1;
                if (arr[mid].d.getTime() <= endTime) lo = mid; else hi = mid - 1;
            }
            const endIdx = lo;

            const totalLen = arr.length;
            this.currentHandle1Pos = startIdx / totalLen;
            this.currentHandle2Pos = (endIdx + 1) / totalLen
                - this.conf.sliderHandleWidth / this.width;

            if (this.currentHandle2Pos <= this.currentHandle1Pos) {
                this.currentHandle2Pos = this.currentHandle1Pos
                    + this.conf.sliderHandleWidth / this.width;
            }
            this.currentHandle1Pos = Math.max(0, this.currentHandle1Pos);
            this.currentHandle2Pos = Math.min(
                1 - this.conf.sliderHandleWidth / this.width,
                this.currentHandle2Pos
            );

            this._fullRedraw();
            this.redrawGraph();
        }

        /** Navigate to the range from clickedDate to the next milestone of the given type */
        _navigateToMilestoneEntry(clickedDate, type, labelText) {
            const clickedTime = clickedDate.getTime();
            // econ, fina, trea are the same role across different ministry names
            const matchTypes = (type === 'econ' || type === 'fina' || type === 'trea')
                ? ['econ', 'fina', 'trea']
                : [type];
            let nextMilestone = null;
            for (const m of this.o.milestones) {
                if (m.d.getTime() > clickedTime && m.p.some(entry => matchTypes.includes(entry.t))) {
                    nextMilestone = m;
                    break;
                }
            }
            const endDate = nextMilestone
                ? nextMilestone.d
                : this.data[0].data[this.data[0].data.length - 1].d;
            this.pinnedMilestoneData = null;
            this.milestoneNavLabel = labelText || null;
            this.currentView = null;

            const startTime = clickedDate.getTime();
            const endTime   = endDate.getTime();

            for (const d of this.data) {
                const base = d.data.slice(d.allTimeIndex);
                // first index >= startDate
                let lo = 0, hi = base.length - 1;
                while (lo < hi) {
                    const mid = (lo + hi) >> 1;
                    if (base[mid].d.getTime() < startTime) lo = mid + 1; else hi = mid;
                }
                const si = lo;
                // last index <= endDate
                lo = 0; hi = base.length - 1;
                while (lo < hi) {
                    const mid = (lo + hi + 1) >> 1;
                    if (base[mid].d.getTime() <= endTime) lo = mid; else hi = mid - 1;
                }
                const ei = lo;
                d.currentData = base.slice(si, ei + 1);
            }

            this.currentHandle1Pos = null;
            this.currentHandle2Pos = null;
            this._fullRedraw();
        }

        /** Switch to a different time-range view and redraw the entire chart */
        changeView() {
            this.milestoneNavLabel = null;
            this.currentHandle1Pos = null;
            this.currentHandle2Pos = null;
            this._fullRedraw();
        }
    }

    ResponsiveChart.conf = {
        /* Default initial time-range view */
        defaultInitialView: 'fiveYears',

        /* Height of the chart graphic in pixels */
        height: 400,
        /* Left margin of the chart SVG (where the Y axis resides) */
        leftMargin: 0,
        /* Bottom margin of the chart SVG (where the X axis resides) */
        bottomMargin: 30,

        /* Viewport width below which mobile layout is used */
        minWidthCutover: 480,
        /* Horizontal margin applied on mobile */
        minWidthContainerMargin: 10,
        /* Number of ticks on the time axis when on mobile */
        minWidthTicks: 5,
        /* Viewport width above which the chart stops growing */
        maxWidthCutover: 1200,
        /* Horizontal margin applied on all non-mobile sizes */
        genWidthCutoverMargin: 14,

        /* Height of the slider container div */
        sliderContainerHeight: 60,
        /* Width of each drag handle rect */
        sliderHandleWidth: 10,
        /* Height of the highlighted range box inside the slider */
        sliderBoxHeight: 40,

        /* Background colour used for tooltip and milestone panels */
        panelsBGColor: '#dddddd',

        /* Width of the tooltip background rect */
        toolTipContainerBGWidth: 240,
        /* Horizontal margin between tooltip and the nearest chart edge */
        toolTipContainerXMargin: 10,
        /* Top margin of the tooltip container */
        toolTipContainerTopMargin: 10,
        /* Padding from the top of the tooltip background to the date label */
        toolTipBGTopPadding: 30,
        /* Padding from the last value label to the bottom of the tooltip background */
        toolTipBGBottomPadding: 20,
        /* Left padding for all text elements inside the tooltip */
        toolTipLeftPadding: 16,
        /* Vertical spacing between value text elements inside the tooltip */
        toolTipTextsSize: 20,

        /* Width and height of the clickable milestone marker rectangles */
        milestonesRectWidth: 20,
        milestonesRectHeight: 10,
        /* Width of the milestone detail panel background */
        milestonesBGWidth: 300,
        /* Gap between the bottom of the milestone panel and the X axis */
        milestonesContainerBottomMargin: 10,
        /* Padding inside the milestone detail panel */
        milestonesTopPadding: 30,
        milestonesLeftPadding: 20,
        milestonesBottomPadding: 30,
        /* Vertical line-height for each text line in the milestone panel */
        milestonesTextSize: 22,

        /*
         * Time-range view buttons.
         * Each entry: { view: [days, months, years], text: string, id: string }
         * The view array offsets are subtracted from the last data date to find the view start.
         */
        views: [
            { view: [3, 0], text: '3 Months',   id: 'threeMonths' },
            { view: [0, 1], text: '1 Year',     id: 'oneYear'     },
            { view: [0, 5], text: '5 Years',    id: 'fiveYears'   },
            { view: null,   text: 'All Records', id: 'allTime'    },
        ],

        /* UI language strings */
        lang: {
            showEvents: 'Show Events',
        },

        /* Whether to show the start/end value and % change results pane below the slider */
        showResultsPane: true,

        /* When true, appends a "%" symbol to every formatted value in the tooltip and Y axis.
         * Use this for charts whose data represents percentages. */
        addPercent: false,
        /* Number of decimal places used when addPercent is true */
        numberOfDigits: 2,

        /* Colour for the auto-generated alternating time-period background bands */
        alternateBandColor: 'rgba(0,0,0,0.04)',

        /* Time-period background bands drawn behind the chart lines.
         * Each entry: { start: "YYYY-MM-DD", end: "YYYY-MM-DD", color: string,
         *               label: string, labelColor: string }
         */
        backgroundBands: [],
    };

    // ── ResponsiveVariations ─────────────────────────────────────────────────────

    class ResponsiveVariations extends ResponsiveBase {
        constructor(options) {
            super();
            this.o = options;
            this.data = options.data;
            this._fmt = genUtils.localeFormatters[options.numberLocale] || genUtils.localeFormatters.es;
            this.lastDay = [];
            this.dailyVariations = [];
            this.monthlyVariations = [];
            this.annualVariations = [];
            this.conf = { ...ResponsiveVariations.conf, ...options.conf };
            this.conf.lang = { ...this.conf.lang, locale: genUtils.dateLocales[options.numberLocale] || genUtils.dateLocales.es };
            this._defaultLeftMargin = this.conf.leftMargin;
            this.init();
        }

        /* Internal Variables

         this.conf                      — The merged configuration (ResponsiveVariations.conf overridden by options.conf)
         this.width: INT                — Current chart width, calculated from screen width and conf parameters
         this.showToolTip: BOOL         — Whether to show the hover tooltip (false on mobile)
         this.showSmallSourceNames: BOOL — Whether to show compact source-name labels (true on mobile)

         this.data [{
             data: [{v, d}]             — Full data array for this series
         }]                             — one entry per series

         this.lastDay: []               — The last date for each data source (indexed by series position)
         this.dailyVariations: []       — Computed daily variation bars for each series
         this.monthlyVariations: []     — Computed monthly variation bars for each series
         this.annualVariations: []       — Computed annual variation bars for each series

         this.currentView: STRING       — Active view key: "daily"|"monthly"|"annual"

         // D3 Elements
         this.container                 — div#{options.containerId}       — outer wrapper
         this.graphContainer            — div#graph-container-{id}        — holds the chart SVG
         this.graphSvg                  — svg#graph-svg-{id}              — the bar chart SVG
         this.viewMenu                  — div                              — tab buttons (Daily / Monthly / Annual)
         this.viewExplanation           — div                              — description text below the tabs

         this.toolTipContainer          — svg:g     — tooltip group
         this.toolTipBackground         — svg:rect  — tooltip background rect
         this.toolTipDate               — svg:text  — date/period label in the tooltip
         this.toolTipTexts              — [svg:text] — one value-label per series

         this.sourceNamesContainer      — div       — mobile source-name labels container
         */

        /* Initialize the chart: process data, calculate variations, build DOM, draw */
        init() {
            this.postLoad();
            this.calculateDailyVariations();
            this.calculateMonthlyVariations();
            this.calculateAnnualVariations();
            this.calculateWidth();
            this.generateBasicElements();
            this.generateViewsMenu();
            this.draw();
            this.fillViewExplanation();
        }

        postLoad() {
            _sliceDataToCommonTimeframe(this.data);
            this.lastDay = this.data.map(series => series.data[series.data.length - 1].d);
            this.currentView = this.o.initialView || this.conf.defaultInitialView;
        }

        /*
         * Calculate daily percentage variations over the last 30 days.
         * Populates this.dailyVariations[i] for each series.
         */
        calculateDailyVariations() {
            for (let i = 0; i < this.data.length; i++) {
                const data = this.data[i].data;
                const lastDayMinus31 = new Date(this.lastDay[i]);
                lastDayMinus31.setDate(this.lastDay[i].getDate() - DAILY_LOOKBACK_DAYS);

                // Find the data index that is 30+ days before lastDay
                let m = data.length - 1;
                let searchIndex = new Date(this.lastDay[i]);
                while (searchIndex.getTime() > lastDayMinus31.getTime()) {
                    m--;
                    searchIndex = data[m].d;
                }

                const tmp = [];
                const index = new Date(data[m].d);
                while (m < data.length) {
                    if (genUtils.formatDate(data[m].d) === genUtils.formatDate(index)) {
                        if (m === 0) { m++; index.setDate(index.getDate() + 1); continue; }
                        const vr = data[m].v - data[m - 1].v;
                        const v = data[m - 1].v !== 0 ? (vr / data[m - 1].v) * PERCENT : 0;
                        tmp.push({ d: genUtils.formatDate(data[m].d), v, vr });
                        m++;
                    } else {
                        tmp.push({ d: genUtils.formatDate(index), v: 0 });
                    }
                    index.setDate(index.getDate() + 1);
                }
                this.dailyVariations[i] = tmp;
            }
        }

        /*
         * Calculate month-over-month percentage variations for the last 12 months.
         * Populates this.monthlyVariations[i] for each series.
         */
        calculateMonthlyVariations() {
            for (let i = 0; i < this.data.length; i++) {
                const data = this.data[i].data;
                const twelveMonthsAgo = new Date(this.lastDay[i]);
                twelveMonthsAgo.setMonth(twelveMonthsAgo.getMonth() - MONTHLY_LOOKBACK_MONTHS, 1);

                // Find data index 12 months ago
                let m = data.length - 1;
                let searchIndex = new Date(this.lastDay[i]);
                while (searchIndex.getTime() >= twelveMonthsAgo.getTime()) {
                    m--;
                    searchIndex = data[m].d;
                }

                // Collect the last value of each month
                const tmp = [];
                let lastMonth = genUtils.formatDateNoDay(data[m].d);
                for (; m < data.length; m++) {
                    if (genUtils.formatDateNoDay(data[m].d) !== lastMonth) {
                        tmp.push({ d: genUtils.formatDateNoDay(data[m - 1].d), v: data[m - 1].v });
                        lastMonth = genUtils.formatDateNoDay(data[m].d);
                    }
                }
                tmp.push({ d: genUtils.formatDateNoDay(data[data.length - 1].d), v: data[data.length - 1].v });

                const final = [];
                for (let n = 1; n < tmp.length; n++) {
                    const vr = tmp[n].v - tmp[n - 1].v;
                    const v = tmp[n - 1].v !== 0 ? (vr / tmp[n - 1].v) * PERCENT : 0;
                    final.push({ d: tmp[n].d, v, vr });
                }
                this.monthlyVariations[i] = final;
            }
        }

        /*
         * Calculate year-over-year percentage variations for all years on record.
         * Populates this.annualVariations[i] for each series.
         */
        calculateAnnualVariations() {
            for (let i = 0; i < this.data.length; i++) {
                const data = this.data[i].data;
                const tmp = [];
                let lastYear = data[0].d.getFullYear();
                for (let m = 0; m < data.length - 1; m++) {
                    if (data[m].d.getFullYear() !== lastYear) {
                        tmp.push({ d: data[m - 1].d.getFullYear(), v: data[m - 1].v });
                        lastYear = data[m].d.getFullYear();
                    }
                }
                // Capture the last data point (current year's most recent value)
                tmp.push({ d: data[data.length - 1].d.getFullYear(), v: data[data.length - 1].v });

                const final = [];
                for (let n = 1; n < tmp.length; n++) {
                    const vr = tmp[n].v - tmp[n - 1].v;
                    const v = tmp[n - 1].v !== 0 ? (vr / tmp[n - 1].v) * PERCENT : 0;
                    final.push({ d: tmp[n].d, v, vr });
                }
                this.annualVariations[i] = final;
            }
        }

        /* Generate the basic container DOM elements (container, view menu, graph container) */
        generateBasicElements() {
            this.container = d3.select(`#${this.o.containerId}`);
            this.viewMenu = this.container.append('div')
                .attr('id', this._id('views-menu'))
                .attr('class', 'view-menu');
            this.graphContainer = this.container.append('div').attr('id', this._id('graph-container'));
        }

        /* Generate the Daily / Monthly / Annual tab buttons */
        generateViewsMenu() {
            const daily   = this.viewMenu.append('a').attr('href', '#').html(this.conf.lang.daily).attr('id', this._id('daily'));
            const monthly = this.viewMenu.append('a').attr('href', '#').html(this.conf.lang.monthly).attr('id', this._id('monthly'));
            const annual  = this.viewMenu.append('a').attr('href', '#').html(this.conf.lang.annual).attr('id', this._id('annual'));

            switch (this.currentView) {
                case 'daily':   daily.attr('class', CSS_ACTIVE);   break;
                case 'monthly': monthly.attr('class', CSS_ACTIVE); break;
                case 'annual':  annual.attr('class', CSS_ACTIVE);  break;
            }

            const makeClickHandler = (view) => (event) => {
                event.preventDefault();
                if (this.currentView !== view) {
                    this.currentView = view;
                    this.changeView(view);
                    this.fillViewExplanation();
                    this._setActiveView(view);
                }
            };

            daily.on('click',   makeClickHandler('daily'));
            monthly.on('click', makeClickHandler('monthly'));
            annual.on('click',  makeClickHandler('annual'));
        }

        draw() {
            let variations;
            switch (this.currentView) {
                case 'annual':  variations = this.annualVariations;  break;
                case 'daily':   variations = this.dailyVariations;   break;
                case 'monthly': default: variations = this.monthlyVariations; break;
            }

            this.graphSvg = this.graphContainer.append('svg')
                .attr('id', this._id('graph-svg'))
                .attr('height', this.conf.height)
                .attr('width', this.width);

            const allDataPoints = variations.flat();
            const yExtent = d3.extent(allDataPoints, d => d.v);
            const xLabelHeight = (this.data.length > 1) ? this.conf.xLabelHeight : 0;
            const actualHeight = this.conf.height - this.conf.topMargin - this.conf.bottomMargin - xLabelHeight;
            const yScale = d3.scaleLinear().domain(yExtent).range([actualHeight, 0]).nice();
            this.conf.leftMargin = this._requiredLeftMargin(yScale, this._defaultLeftMargin);
            const innerWidth = this.width - this.conf.leftMargin;
            const xScale = d3.scaleBand().domain(d3.range(variations[0].length)).rangeRound([0, innerWidth]);
            const rangeBand = xScale.bandwidth();
            const iPos = Math.floor(rangeBand / variations.length);
            const barWidth = iPos - this.conf.boxLeftMargin;
            const zeroPos = yScale(0) + this.conf.topMargin;

            for (let j = 0; j < variations[0].length; j++) {
                if (j % 2 === 0) {
                    this.graphSvg.append('rect')
                        .attr('x', this.conf.leftMargin + (j * rangeBand))
                        .attr('y', this.conf.topMargin)
                        .attr('width', rangeBand)
                        .attr('height', actualHeight)
                        .attr('fill', this.conf.alternateBandColor);
                }
            }

            this.graphSvg.append('line')
                .attr('x1', this.conf.leftMargin - 4).attr('y1', zeroPos)
                .attr('x2', this.width).attr('y2', zeroPos)
                .attr('stroke', 'black');

            const barData = variations.flatMap((seriesVars, i) =>
                seriesVars.map((bar, j) => ({ bar, i, j }))
            );
            const barR = 2;
            const roundedBarPath = (x, w, h, positive) => {
                const r = Math.min(barR, w / 2, Math.abs(h) / 2);
                if (positive) {
                    return `M${x},${zeroPos} L${x},${zeroPos - h + r} Q${x},${zeroPos - h} ${x + r},${zeroPos - h} L${x + w - r},${zeroPos - h} Q${x + w},${zeroPos - h} ${x + w},${zeroPos - h + r} L${x + w},${zeroPos} Z`;
                } else {
                    const top = zeroPos;
                    const bot = zeroPos + Math.abs(h);
                    return `M${x},${top} L${x + w},${top} L${x + w},${bot - r} Q${x + w},${bot} ${x + w - r},${bot} L${x + r},${bot} Q${x},${bot} ${x},${bot - r} Z`;
                }
            };
            this.graphSvg.selectAll('path.bar')
                .data(barData)
                .enter()
                .append('path')
                .attr('class', 'bar')
                .attr('d', ({ bar, i, j }) => {
                    const x = this.conf.leftMargin + (j * rangeBand) + (i * iPos);
                    const y = yScale(bar.v) + this.conf.topMargin;
                    const h = Math.abs(zeroPos - y);
                    return roundedBarPath(x, barWidth, h, bar.v >= 0);
                })
                .attr('fill', ({ i }) => this.data[i].stroke);

            const yAxis = d3.axisLeft(yScale)
                .tickFormat(d => this._fmt(d));
            this.graphSvg.append('g')
                .attr('class', CSS_AXIS)
                .attr('transform', `translate(${this.conf.leftMargin - this.conf.zeroLinePreAndPos - this.conf.boxLeftMargin},${this.conf.topMargin})`)
                .call(yAxis);

            if (this.data.length > 1) {
                const step = this._xLabelStep(rangeBand);
                this.graphSvg.selectAll('text.x-label')
                    .data(variations[0].filter((_, j) => j % step === 0).map((bar, idx) => ({ d: bar.d, j: idx * step })))
                    .enter()
                    .append('text')
                    .attr('class', 'x-label')
                    .attr('x', ({ j }) => this.conf.leftMargin + (j * rangeBand) + rangeBand / 2)
                    .attr('y', this.conf.topMargin + actualHeight + xLabelHeight - 6)
                    .attr('text-anchor', 'middle')
                    .attr('font-size', this.conf.xLabelFontSize)
                    .attr('fill', '#555')
                    .text(({ d }) => this._formatXLabel(d));
            }

            this._setActiveView(this.currentView);

            if (this.showToolTip) {
                this._setupVariationTooltip(variations, rangeBand);
            }

            if (this.showSmallSourceNames && this.data.length > 1) {
                this.sourceNamesContainer = this.container.append('div').attr('class', 'source-names right');
                for (const { stroke, name } of this.data) {
                    this.sourceNamesContainer.append('div').attr('style', `color:${stroke};`).text(name);
                }
            }

            this.viewExplanation = this.container.append('div').attr('class', 'view-menu-explanation');
        }

        _xLabelStep(rangeBand) {
            if (rangeBand >= 40) return 1;
            if (rangeBand >= 20) return 3;
            return 7;
        }

        _formatXLabel(d) {
            if (this.currentView === 'annual') return String(d);
            if (this.currentView === 'monthly') {
                const [y, m] = d.split('-');
                const date = new Date(+y, +m - 1, 1);
                return date.toLocaleString(this.conf.lang.locale || 'default', { month: 'short', year: '2-digit' });
            }
            const [, m, day] = d.split('-');
            return `${+day}/${+m}`;
        }

        /* Set up the hover tooltip for the variations bar chart */
        _setupVariationTooltip(variations, rangeBand) {
            this.mouseOverRect = this.graphSvg.append('svg:rect')
                .attr('x', this.conf.leftMargin)
                .attr('width', this.width)
                .attr('height', this.conf.height)
                .attr('fill', 'none')
                .attr('pointer-events', 'all');

            this.toolTipContainer = this.graphSvg.append('g')
                .attr('transform', `translate(${this.conf.leftMargin + this.conf.toolTipLeftMargin},${this.conf.topMargin + this.conf.toolTipTopMargin})`);

            const toolTipBGHeight = this.conf.toolTipTopPadding + (this.conf.toolTipLineHeight * this.data.length) + this.conf.toolTipBottomPadding;
            this.toolTipBGWidth = this.conf.toolTipContainerBGWidth;
            this.toolTipBackground = this.toolTipContainer.append('rect')
                .attr('height', toolTipBGHeight)
                .attr('width', this.toolTipBGWidth)
                .attr('x', 0).attr('y', 0)
                .attr('rx', 6).attr('ry', 6)
                .attr('fill', 'none');

            this.toolTipDate = this.toolTipContainer.append('text')
                .attr('x', this.conf.toolTipLeftPadding)
                .attr('y', this.conf.toolTipTopPadding);

            this.toolTipTexts = this.data.map((series, i) =>
                this.toolTipContainer.append('text')
                    .attr('x', this.conf.toolTipLeftPadding)
                    .attr('y', this.conf.toolTipTopPadding + (this.conf.toolTipLineHeight * (i + 1)))
                    .attr('fill', series.stroke)
                    .attr('class', 'tooltip-text')
            );

            // Grow the box at init to fit the widest text that will ever appear.
            {
                const padding = this.conf.toolTipLeftPadding * 2;

                const allVarSets = [this.dailyVariations, this.monthlyVariations, this.annualVariations];

                const worstCaseValues = this.data.map((series, i) => {
                    let maxAbsV = 0;
                    for (const varSet of allVarSets) {
                        if (!varSet[i]) continue;
                        for (const pt of varSet[i]) {
                            if (Math.abs(pt.v) > Math.abs(maxAbsV)) maxAbsV = pt.v;
                        }
                    }
                    return `${series.name}: ${this._fmt(maxAbsV.toFixed(4))}%`;
                });

                const measureText = (text, cssClass) => {
                    const tmp = this.toolTipContainer.append('text')
                        .style('visibility', 'hidden');
                    if (cssClass) tmp.attr('class', cssClass);
                    tmp.text(text);
                    const len = tmp.node().getComputedTextLength();
                    tmp.remove();
                    return len;
                };

                const maxMeasured = Math.max(
                    measureText('2020-12-31', null),
                    ...worstCaseValues.map(s => measureText(s, 'tooltip-text'))
                );

                if (maxMeasured > 0) {
                    const needed = Math.ceil(maxMeasured) + padding;
                    if (needed > this.toolTipBGWidth) {
                        this.toolTipBGWidth = needed;
                        this.toolTipBackground.attr('width', this.toolTipBGWidth);
                    }
                }
            }

            this.mouseOverRect.on('mousemove', (event) => {
                const actualX = d3.pointer(event)[0];
                const x0 = Math.floor((actualX - this.conf.leftMargin) / rangeBand);
                if (x0 >= 0 && x0 <= variations[0].length - 1) {
                    this.toolTipBackground.attr('fill', this.conf.panelsBGColor);
                    this.toolTipDate.text(variations[0][x0].d);
                    for (let i = 0; i < this.data.length; i++) {
                        this.toolTipTexts[i].text(`${this.data[i].name}: ${this._fmt(variations[i][x0].v.toFixed(4))}%`);
                    }
                    if (actualX < this.width / 2) {
                        this.toolTipContainer.attr('transform', `translate(${this.width - this.conf.toolTipLeftMargin - this.toolTipBGWidth},${this.conf.topMargin + this.conf.toolTipTopMargin})`);
                    } else {
                        this.toolTipContainer.attr('transform', `translate(${this.conf.leftMargin + this.conf.toolTipLeftMargin},${this.conf.topMargin + this.conf.toolTipTopMargin})`);
                    }
                }
            });

            this.mouseOverRect.on('mouseout', () => {
                this.toolTipBackground.attr('fill', 'none');
                this.toolTipDate.text('');
                for (const t of this.toolTipTexts) t.text('');
            });
        }

        fillViewExplanation() {
            switch (this.currentView) {
                case 'daily':   this.viewExplanation.html(this.conf.lang.dailyExp);   break;
                case 'monthly': this.viewExplanation.html(this.conf.lang.monthlyExp); break;
                case 'annual':  this.viewExplanation.html(this.conf.lang.annualExp);  break;
            }
        }

        /** Resize the chart in response to a window resize event */
        resize() {
            this.cleanUp();
            this.calculateWidth();
            this.draw();
            this.fillViewExplanation();
        }

        /* Remove all DOM elements and null out references to assist garbage collection */
        cleanUp() {
            this.toolTipDate = null;
            this.toolTipBackground = null;
            if (this.toolTipContainer) this.toolTipContainer.remove();
            this.toolTipContainer = null;
            if (this.sourceNamesContainer) {
                this.sourceNamesContainer.remove();
                this.sourceNamesContainer = null;
            }
            if (this.viewExplanation) this.viewExplanation.remove();
            this.viewExplanation = null;
            if (this.graphSvg) this.graphSvg.remove();
            this.graphSvg = null;
        }

        /* Switch to a different variation view (daily/monthly/annual) and redraw */
        changeView() {
            this.cleanUp();
            this.draw();
        }
    }

    ResponsiveVariations.conf = {
        /* Default initial variation view */
        defaultInitialView: 'monthly',

        /* Height of the chart graphic in pixels */
        height: 400,
        /* Left margin of the chart SVG (where the Y axis resides) */
        leftMargin: 50,
        /* Top and bottom margins (necessary to fit axis text) */
        topMargin: 10,
        bottomMargin: 10,

        /* Viewport width below which mobile layout is used */
        minWidthCutover: 480,
        /* Horizontal margin applied on mobile */
        minWidthContainerMargin: 10,
        /* Viewport width above which the chart stops growing */
        maxWidthCutover: 1200,
        /* Horizontal margin applied on all non-mobile sizes */
        genWidthCutoverMargin: 14,

        /* Background colour used for tooltip panels */
        panelsBGColor: '#cccccc',

        /* Extra space added before and after the zero line on both sides */
        zeroLinePreAndPos: 4,
        /* Left margin applied to each bar within its band */
        boxLeftMargin: 2,

        /* Alternating background colour for multi-series period bands */
        alternateBandColor: 'rgba(0,0,0,0.045)',
        /* Space reserved at the bottom of the SVG for X-axis labels (multi-series only) */
        xLabelHeight: 22,
        /* Font size for X-axis period labels */
        xLabelFontSize: 11,

        /* Width of the tooltip background rect */
        toolTipContainerBGWidth: 260,
        /* Top and left margin of the tooltip relative to the SVG */
        toolTipLeftMargin: 10,
        toolTipTopMargin: 10,
        /* Left padding for all text elements inside the tooltip */
        toolTipLeftPadding: 14,
        /* Top padding (distance from tooltip top to the date label baseline) */
        toolTipTopPadding: 28,
        /* Vertical line-height between tooltip text rows */
        toolTipLineHeight: 20,
        /* Padding from the last text row to the bottom of the tooltip background */
        toolTipBottomPadding: 30,

        /* UI language strings */
        lang: {
            daily:      'Daily',
            monthly:    'Monthly',
            annual:     'Annual',
            dailyExp:   'From the last recorded change, previous or equal to 30 days before the last record.',
            monthlyExp: 'Last 12 months.',
            annualExp:  'All of the years on record.',
        },
    };

    // ── Public API ───────────────────────────────────────────────────────────────
    global.genUtils = genUtils;
    global.ResponsiveChartLibraryDataLoader = ResponsiveChartLibraryDataLoader;
    global.ResponsiveChart = ResponsiveChart;
    global.ResponsiveVariations = ResponsiveVariations;
    // Backward-compat aliases used in existing HTML consumers
    global.responsiveChart = ResponsiveChart;
    global.responsiveVariations = ResponsiveVariations;

})(window);
