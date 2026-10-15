// http1-reuse-bench.go: counts new TCP connections and wall time when an
// HTTP/1 client closes a response body without reading it.
// Run with:  GOTOOLCHAIN=go1.26.2 go run http1-reuse-bench.go
//            GOTOOLCHAIN=go1.27.0 go run http1-reuse-bench.go
// Optional:  -rtt 20ms adds a sleep to every dial to imitate network latency.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"runtime"
	"sort"
	"strings"
	"sync/atomic"
	"time"
)

var (
	rtt   = flag.Duration("rtt", 0, "sleep added to every dial")
	n     = flag.Int("n", 100, "sequential requests per case")
	reps  = flag.Int("reps", 5, "repetitions per case (median time reported)")
	newC  atomic.Int64
	rxB   atomic.Int64 // bytes the client actually received
	slowD = flag.Duration("slow", 100*time.Millisecond, "pause in the slow-body case")
)

type cnt struct{ net.Conn }

func (c *cnt) Read(b []byte) (int, error) {
	k, err := c.Conn.Read(b)
	rxB.Add(int64(k))
	return k, err
}

func main() {
	flag.Parse()
	mux := http.NewServeMux()
	// /size?n=BYTES : fixed Content-Length body
	mux.HandleFunc("/size", func(w http.ResponseWriter, r *http.Request) {
		var sz int
		fmt.Sscan(r.URL.Query().Get("n"), &sz)
		w.Header().Set("Content-Length", fmt.Sprint(sz))
		w.Write([]byte(strings.Repeat("x", sz)))
	})
	// /slow?pause=DUR : 1 KB, flush, pause, then 1 KB more (chunked)
	mux.HandleFunc("/slow", func(w http.ResponseWriter, r *http.Request) {
		d, _ := time.ParseDuration(r.URL.Query().Get("pause"))
		w.Write([]byte(strings.Repeat("x", 1024)))
		w.(http.Flusher).Flush()
		time.Sleep(d)
		w.Write([]byte(strings.Repeat("y", 1024)))
	})
	mux.HandleFunc("/close", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Connection", "close")
		w.Write([]byte(strings.Repeat("x", 4096)))
	})
	mux.HandleFunc("/json", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintln(w, `{"a":1}`) // trailing newline after the object
	})
	// /jsonchunked : same object, but chunked (no Content-Length)
	mux.HandleFunc("/jsonchunked", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, `{"a":1}`)
		w.(http.Flusher).Flush()
		fmt.Fprint(w, "\n")
	})
	ln, _ := net.Listen("tcp", "127.0.0.1:0")
	srv := &http.Server{Handler: mux, ConnState: func(c net.Conn, s http.ConnState) {
		if s == http.StateNew {
			newC.Add(1)
		}
	}}
	go srv.Serve(ln)
	base := "http://" + ln.Addr().String()

	type tc struct {
		name string
		path string
		read bool // fully read the body before closing
		fn   func(*http.Response)
	}
	var cases []tc
	for _, sz := range []int{1024, 65536, 262143, 262144, 262145, 1 << 20} {
		cases = append(cases, tc{fmt.Sprintf("close-unread size=%d", sz), fmt.Sprintf("/size?n=%d", sz), false, nil})
	}
	cases = append(cases, tc{"control: read-all size=65536", "/size?n=65536", true, nil})
	cases = append(cases,
		tc{"slow body, pause=10ms", "/slow?pause=10ms", false, nil},
		tc{"slow body, pause=" + slowD.String(), "/slow?pause=" + slowD.String(), false, nil},
		tc{"Connection: close response", "/close", false, nil},
		tc{"json.Decode leaves newline", "/json", false, func(r *http.Response) {
			var v map[string]int
			json.NewDecoder(r.Body).Decode(&v)
		}},
		tc{"json.Decode, chunked", "/jsonchunked", false, func(r *http.Response) {
			var v map[string]int
			json.NewDecoder(r.Body).Decode(&v)
		}},
	)

	fmt.Printf("# %s rtt=%s n=%d reps=%d\n", runtime.Version(), *rtt, *n, *reps)
	fmt.Printf("%-34s %8s %10s %11s\n", "case", "newConns", "median_ms", "KB/request")
	for _, c := range cases {
		var times []float64
		var conns, rx int64
		for r := 0; r < *reps; r++ {
			tr := &http.Transport{
				ForceAttemptHTTP2: false,
				DialContext: func(ctx context.Context, nw, a string) (net.Conn, error) {
					if *rtt > 0 {
						time.Sleep(*rtt)
					}
					c, err := (&net.Dialer{}).DialContext(ctx, nw, a)
					if err != nil {
						return nil, err
					}
					return &cnt{Conn: c}, nil
				},
			}
			cl := &http.Client{Transport: tr}
			before, rxBefore := newC.Load(), rxB.Load()
			t0 := time.Now()
			for i := 0; i < *n; i++ {
				resp, err := cl.Get(base + c.path)
				if err != nil {
					panic(err)
				}
				switch {
				case c.fn != nil:
					c.fn(resp)
				case c.read:
					io.Copy(io.Discard, resp.Body)
				}
				resp.Body.Close()
			}
			times = append(times, float64(time.Since(t0).Microseconds())/1000)
			conns = newC.Load() - before
			rx = rxB.Load() - rxBefore
			tr.CloseIdleConnections()
			time.Sleep(300 * time.Millisecond) // let stragglers finish
		}
		sort.Float64s(times)
		fmt.Printf("%-34s %8d %10.1f %11.1f\n", c.name, conns, times[len(times)/2], float64(rx)/1024/float64(*n))
	}
}
