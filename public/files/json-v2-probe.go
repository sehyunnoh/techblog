// json-v2-probe.go: compares encoding/json (v1) with encoding/json/v2 on Go 1.27.
//
//	go run json-v2-probe.go behavior   # what each one accepts, rejects and emits
//	go run json-v2-probe.go bench      # Marshal / Unmarshal timings (takes a few minutes)
//
// Needs Go 1.27 or newer. Reads nothing, writes nothing, touches no network.
package main

import (
	"bytes"
	"encoding/json"
	"encoding/json/jsontext"
	jsonv2 "encoding/json/v2"
	"fmt"
	"os"
	"runtime"
	"sort"
	"strings"
	"testing"
	"time"
)

// ---------- behavior ----------

func show(v any, err error) string {
	if err != nil {
		msg := err.Error()
		if len(msg) > 70 {
			msg = msg[:70] + "..."
		}
		return "ERROR: " + msg
	}
	return fmt.Sprintf("%+v", v)
}

func row(name string, v1, v2 string) {
	mark := "same"
	switch {
	case strings.HasPrefix(v1, "ERROR") && strings.HasPrefix(v2, "ERROR"):
		mark = "both error"
	case v1 != v2:
		mark = "DIFFERENT"
	}
	fmt.Printf("%-34s | v1: %-40s | v2: %-40s | %s\n", name, v1, v2, mark)
}

type named struct {
	Name string `json:"name"`
}
type withSlices struct {
	S []int
	M map[string]int
}
type inner struct{}
type omit struct {
	In  inner     `json:"in,omitempty"`
	T   time.Time `json:"t,omitempty"`
	Z   time.Time `json:"z,omitzero"`
	Ptr *int      `json:"ptr,omitempty"`
}

func behavior() {
	fmt.Println("go", runtime.Version())
	// 1 invalid UTF-8 on decode
	{
		var a, b string
		e1 := json.Unmarshal([]byte("\"a\xffb\""), &a)
		e2 := jsonv2.Unmarshal([]byte("\"a\xffb\""), &b)
		row("decode invalid UTF-8", show(fmt.Sprintf("%q", a), e1), show(fmt.Sprintf("%q", b), e2))
	}
	// 2 invalid UTF-8 on encode
	{
		o1, e1 := json.Marshal("a\xffb")
		o2, e2 := jsonv2.Marshal("a\xffb")
		row("encode invalid UTF-8", show(string(o1), e1), show(string(o2), e2))
	}
	// 3 duplicate names
	{
		in := []byte(`{"a":1,"a":2}`)
		var s1, s2 struct {
			A int `json:"a"`
		}
		e1 := json.Unmarshal(in, &s1)
		e2 := jsonv2.Unmarshal(in, &s2)
		row("duplicate name, struct", show(s1, e1), show(s2, e2))
		var m1, m2 map[string]int
		e1 = json.Unmarshal(in, &m1)
		e2 = jsonv2.Unmarshal(in, &m2)
		row("duplicate name, map", show(m1, e1), show(m2, e2))
	}
	// 4 case-insensitive field match
	{
		in := []byte(`{"NAME":"x"}`)
		var a, b named
		e1 := json.Unmarshal(in, &a)
		e2 := jsonv2.Unmarshal(in, &b)
		row("field name case", show(a, e1), show(b, e2))
	}
	// 5 nil slice and map
	{
		o1, e1 := json.Marshal(withSlices{})
		o2, e2 := jsonv2.Marshal(withSlices{})
		row("nil slice and nil map", show(string(o1), e1), show(string(o2), e2))
	}
	// 6 omitempty and omitzero
	{
		o1, e1 := json.Marshal(omit{})
		o2, e2 := jsonv2.Marshal(omit{})
		row("omitempty/omitzero", show(string(o1), e1), show(string(o2), e2))
	}
	// 7 time.Duration
	{
		o1, e1 := json.Marshal(time.Second)
		o2, e2 := jsonv2.Marshal(time.Second)
		row("time.Duration", show(string(o1), e1), show(string(o2), e2))
	}
	// 8 trailing data
	{
		in := []byte(`{"a":1} junk`)
		var s1, s2 struct {
			A int `json:"a"`
		}
		e1 := json.Unmarshal(in, &s1)
		e2 := jsonv2.Unmarshal(in, &s2)
		row("trailing junk, Unmarshal", show(s1, e1), show(s2, e2))
		var d1, d2 struct {
			A int `json:"a"`
		}
		e1 = json.NewDecoder(strings.NewReader(string(in))).Decode(&d1)
		e2 = jsonv2.UnmarshalRead(strings.NewReader(string(in)), &d2)
		row("trailing junk, reader", show(d1, e1), show(d2, e2))
	}
	// 9 unknown fields
	{
		in := []byte(`{"a":1,"extra":2}`)
		var s1, s2 struct {
			A int `json:"a"`
		}
		e1 := json.Unmarshal(in, &s1)
		e2 := jsonv2.Unmarshal(in, &s2)
		row("unknown field", show(s1, e1), show(s2, e2))
	}
	// 10 HTML escaping
	{
		o1, e1 := json.Marshal("<a&b>")
		o2, e2 := jsonv2.Marshal("<a&b>")
		row("HTML characters", show(string(o1), e1), show(string(o2), e2))
	}
	// 11 map key order across 30 runs
	{
		m := map[string]int{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7, "h": 8}
		seen1 := map[string]bool{}
		seen2 := map[string]bool{}
		for i := 0; i < 30; i++ {
			a, _ := json.Marshal(m)
			b, _ := jsonv2.Marshal(m)
			seen1[string(a)] = true
			seen2[string(b)] = true
		}
		row("map key order, distinct of 30", fmt.Sprint(len(seen1)), fmt.Sprint(len(seen2)))
		det, _ := jsonv2.Marshal(m, jsonv2.Deterministic(true))
		fmt.Printf("%-34s | v2 with Deterministic(true): %s\n", "", det)
	}
	// 12 large integer into any
	{
		var a, b any
		in := []byte(`9007199254740993`)
		e1 := json.Unmarshal(in, &a)
		e2 := jsonv2.Unmarshal(in, &b)
		row("2^53+1 into any", show(fmt.Sprintf("%T %v", a, a), e1), show(fmt.Sprintf("%T %v", b, b), e2))
	}
	// 13 migration: v2 with v1 options reproduces v1 on the cases above
	{
		fmt.Println("--- v2 with json.DefaultOptionsV1() ---")
		opt := json.DefaultOptionsV1()
		var a, b string
		jsonv2.Unmarshal([]byte("\"a\xffb\""), &a)
		e := jsonv2.Unmarshal([]byte("\"a\xffb\""), &b, opt)
		fmt.Printf("invalid UTF-8 with V1 options: %s\n", show(fmt.Sprintf("%q", b), e))
		var n named
		e = jsonv2.Unmarshal([]byte(`{"NAME":"x"}`), &n, opt)
		fmt.Printf("case-insensitive with V1 options: %s\n", show(n, e))
		o, e := jsonv2.Marshal(withSlices{}, opt)
		fmt.Printf("nil slice and map with V1 options: %s\n", show(string(o), e))
		o, e = jsonv2.Marshal(time.Second, opt)
		fmt.Printf("time.Duration with V1 options: %s\n", show(string(o), e))
		var d struct {
			A int `json:"a"`
		}
		e = jsonv2.Unmarshal([]byte(`{"a":1,"a":2}`), &d, opt)
		fmt.Printf("duplicate name with V1 options: %s\n", show(d, e))
		m := map[string]int{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7, "h": 8}
		seen := map[string]bool{}
		for i := 0; i < 30; i++ {
			x, _ := jsonv2.Marshal(m, opt)
			seen[string(x)] = true
		}
		fmt.Printf("map order with V1 options, distinct of 30: %d\n", len(seen))
	}
}

// ---------- bench ----------

type Rec struct {
	ID      int64             `json:"id"`
	Name    string            `json:"name"`
	Email   string            `json:"email"`
	Active  bool              `json:"active"`
	Score   float64           `json:"score"`
	Tags    []string          `json:"tags"`
	Created string            `json:"created"`
	Attrs   map[string]string `json:"attrs"`
}

func makeRec(i int) Rec {
	return Rec{
		ID: int64(i), Name: fmt.Sprintf("user-%d", i), Email: fmt.Sprintf("user%d@example.com", i),
		Active: i%2 == 0, Score: float64(i) * 1.5, Tags: []string{"alpha", "beta", "gamma"},
		Created: "2026-11-05T10:00:00Z", Attrs: map[string]string{"k1": "v1", "k2": "v2", "k3": "v3"},
	}
}

// Chain is a recursive type with a custom UnmarshalJSON that calls json.Unmarshal.
type Chain struct {
	N    int
	Next *Chain
}
type chainAlias Chain

func (c *Chain) UnmarshalJSON(b []byte) error { return json.Unmarshal(b, (*chainAlias)(c)) }

// ChainFrom is the same shape using the streaming interface.
type ChainFrom struct {
	N    int
	Next *ChainFrom
}
type chainFromAlias ChainFrom

func (c *ChainFrom) UnmarshalJSONFrom(d *jsontext.Decoder) error {
	return jsonv2.UnmarshalDecode(d, (*chainFromAlias)(c))
}

func chainJSON(depth int) []byte {
	var sb strings.Builder
	for i := 0; i < depth; i++ {
		fmt.Fprintf(&sb, `{"N":%d,"Next":`, i)
	}
	sb.WriteString("null")
	sb.WriteString(strings.Repeat("}", depth))
	return []byte(sb.String())
}

const runs = 5

type result struct {
	ns     []float64
	allocs int64
	bytes  int64
}

func measure(f func(b *testing.B)) result {
	var r result
	for i := 0; i < runs; i++ {
		br := testing.Benchmark(f)
		r.ns = append(r.ns, float64(br.NsPerOp()))
		r.allocs = br.AllocsPerOp()
		r.bytes = br.AllocedBytesPerOp()
	}
	sort.Float64s(r.ns)
	return r
}

func (r result) med() float64 { return r.ns[len(r.ns)/2] }

func report(label string, base, other result) {
	fmt.Printf("%-34s base %12.0f ns [%0.0f..%0.0f]  new %12.0f ns [%0.0f..%0.0f]  base/new %.2fx  allocs %d -> %d\n",
		label, base.med(), base.ns[0], base.ns[len(base.ns)-1], other.med(), other.ns[0], other.ns[len(other.ns)-1],
		base.med()/other.med(), base.allocs, other.allocs)
}

func bench() {
	fmt.Println("go", runtime.Version(), runtime.GOOS, runtime.GOARCH, "cpus", runtime.NumCPU(), "runs", runs)

	small := makeRec(1)
	big := make([]Rec, 1000)
	for i := range big {
		big[i] = makeRec(i)
	}
	smallJSON, _ := json.Marshal(small)
	bigJSON, _ := json.Marshal(big)
	var anyBig any
	json.Unmarshal(bigJSON, &anyBig)
	fmt.Printf("payload bytes: small %d, big %d\n", len(smallJSON), len(bigJSON))
	fmt.Println("columns: v1 = encoding/json, v2 = encoding/json/v2 defaults, v2+V1 = v2 with json.DefaultOptionsV1()")
	opt1 := json.DefaultOptionsV1()

	type setup struct {
		name string
		v1   func(b *testing.B)
		v2   func(b *testing.B)
		v2v1 func(b *testing.B)
	}
	cases := []setup{
		{"marshal small struct",
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					json.Marshal(&small)
				}
			},
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					jsonv2.Marshal(&small)
				}
			},
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					jsonv2.Marshal(&small, opt1)
				}
			}},
		{"marshal 1000 structs",
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					json.Marshal(&big)
				}
			},
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					jsonv2.Marshal(&big)
				}
			},
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					jsonv2.Marshal(&big, opt1)
				}
			}},
		{"marshal map[string]any 1000",
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					json.Marshal(&anyBig)
				}
			},
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					jsonv2.Marshal(&anyBig)
				}
			},
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					jsonv2.Marshal(&anyBig, opt1)
				}
			}},
		{"unmarshal small struct",
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					var r Rec
					json.Unmarshal(smallJSON, &r)
				}
			},
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					var r Rec
					jsonv2.Unmarshal(smallJSON, &r)
				}
			},
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					var r Rec
					jsonv2.Unmarshal(smallJSON, &r, opt1)
				}
			}},
		{"unmarshal 1000 structs",
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					var r []Rec
					json.Unmarshal(bigJSON, &r)
				}
			},
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					var r []Rec
					jsonv2.Unmarshal(bigJSON, &r)
				}
			},
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					var r []Rec
					jsonv2.Unmarshal(bigJSON, &r, opt1)
				}
			}},
		{"unmarshal into any, 1000",
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					var r any
					json.Unmarshal(bigJSON, &r)
				}
			},
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					var r any
					jsonv2.Unmarshal(bigJSON, &r)
				}
			},
			func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					var r any
					jsonv2.Unmarshal(bigJSON, &r, opt1)
				}
			}},
	}
	for _, c := range cases {
		a, b, d := measure(c.v1), measure(c.v2), measure(c.v2v1)
		report(c.name+" (v1 vs v2)", a, b)
		report(c.name+" (v1 vs v2+V1)", a, d)
	}

	// Recursive custom unmarshaler
	for _, depth := range []int{10, 100, 400} {
		in := chainJSON(depth)
		a := measure(func(b *testing.B) {
			b.ReportAllocs()
			for i := 0; i < b.N; i++ {
				var c Chain
				if err := json.Unmarshal(in, &c); err != nil {
					b.Fatal(err)
				}
			}
		})
		b2 := measure(func(b *testing.B) {
			b.ReportAllocs()
			for i := 0; i < b.N; i++ {
				var c ChainFrom
				if err := jsonv2.Unmarshal(in, &c); err != nil {
					b.Fatal(err)
				}
			}
		})
		report(fmt.Sprintf("custom unmarshaler depth %d (%dB)", depth, len(in)), a, b2)
	}
	_ = bytes.MinRead
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("usage: go run json-v2-probe.go behavior|bench")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "behavior":
		behavior()
	case "bench":
		bench()
	}
}
