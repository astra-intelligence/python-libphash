/* The C side of the benchmarks: libphash called directly, with no Python in between, so
 * that benchmarks/overhead.py and benchmarks/search.py can set the binding's time for a
 * piece of work beside the time the same work takes in C, on the same build.
 *
 *     bench <min_runs> <min_seconds>
 *
 * It reads one case per line from stdin, fields separated by tabs, and times it the way
 * benchmarks/timing.py times a Python case: one run to warm up, then runs until there
 * have been at least <min_runs> of them and <min_seconds> have passed (at most
 * MAX_RUNS); a run repeats work shorter than MIN_RUN_SECONDS until it lasts that long.
 * It writes one line per case, the time of one item of work in seconds:
 *
 *     {"min": <seconds>, "median": <seconds>, "runs": <runs>}
 *
 * or "error <what>" when the case cannot run. The cases:
 *
 *     load_file      <path>                         ph_load_from_file()
 *     load_memory    <path>                         ph_load_from_memory()
 *     load_pixels    <raw> <w> <h> <channels>       ph_load_from_pixels(), packed rows
 *     hash           <algo> <path>                  one hash of an image loaded once
 *     load_hash      <algo> <path>                  ph_load_from_memory() and one hash
 *     load_multi     <path>                         a load and ph_compute_multi(), 4 hashes
 *     load_separate  <path>                         a load and the 4 hashes one by one
 *     fresh          <algo> <path>                  ph_create(), a file load, a hash, ph_free()
 *     reused         <algo> <path>                  a file load and a hash on a kept context
 *     batch_files    <path> <n> <threads>           ph_hash_files() of n copies, per item
 *     batch_buffers  <path> <n> <threads>           ph_hash_buffers() of n copies, per item
 *     hamming        <n>                            ph_hamming_distance(), per call
 *     metric         <name> <algo> <path> <path2>   a digest comparison, per call
 *     search         <n>                            1 to n: the nearest of n hashes, per hash
 *     search_all     <n>                            n to n: every pair of n hashes, per pair
 *
 * <algo> is a ph_algorithm_t value. The 64-bit hashes are computed by their own
 * ph_compute_*() function and the digests by ph_compute_digest(), as the binding does.
 * <name> is hamming, l2, similarity, radial or histogram. A "hash" case computes the hash
 * of an image whose grayscale image and area grid the first hash cached, as a second
 * call of the binding's hash() on a loaded image does; a "load_hash" case computes them.
 * The hashes of "search" come from a fixed pseudo-random sequence.
 *
 * A line "build_info" instead prints ph_get_build_info(), by which benchmarks/cbench.py
 * checks that the program and the extension link the same build. */

#if !defined(__APPLE__) && !defined(_WIN32)
#    define _POSIX_C_SOURCE 200809L
#endif

#include <libphash.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef __APPLE__
#    include <mach/mach_time.h>
#elif defined(_WIN32)
#    include <windows.h>
#endif

#define MAX_LINE 8192
#define MAX_FIELDS 8
#define MAX_RUNS 100000
#define MIN_RUN_SECONDS 50e-6

/* Seconds on a monotonic clock with a resolution well below a microsecond. */
static double seconds(void) {
#ifdef __APPLE__
    static mach_timebase_info_data_t tb;
    if (tb.denom == 0)
        mach_timebase_info(&tb);
    return (double)mach_absolute_time() * tb.numer / tb.denom * 1e-9;
#elif defined(_WIN32)
    static LARGE_INTEGER freq;
    LARGE_INTEGER now;
    if (freq.QuadPart == 0)
        QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&now);
    return (double)now.QuadPart / (double)freq.QuadPart;
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
#endif
}

static void fail(const char *what, const char *detail) {
    fprintf(stderr, "bench: %s: %s\n", what, detail);
    exit(2);
}

static uint8_t *read_file(const char *path, size_t *out_len) {
    FILE *f = fopen(path, "rb");
    if (!f)
        return NULL;
    uint8_t *buf = NULL;
    size_t len = 0, cap = 0;
    for (;;) {
        if (len == cap) {
            cap = cap ? cap * 2 : 65536;
            uint8_t *grown = (uint8_t *)realloc(buf, cap);
            if (!grown)
                fail("out of memory reading", path);
            buf = grown;
        }
        size_t n = fread(buf + len, 1, cap - len, f);
        len += n;
        if (n == 0)
            break;
    }
    fclose(f);
    *out_len = len;
    return buf;
}

static int to_int(const char *text) {
    char *end;
    long v = strtol(text, &end, 10);
    if (*text == '\0' || *end != '\0')
        fail("not an integer", text);
    return (int)v;
}

/* --- The state of one case ---------------------------------------------------------- */

typedef struct {
    ph_context_t *ctx;
    const char *path;
    uint8_t *data;
    size_t length;
    int algo;
    int width, height, channels;
    int n, threads;
    ph_batch_item_t *items;
    ph_batch_buffer_item_t *buffers;
    uint64_t *hashes;
    ph_digest_t a, b;
    int metric;
    volatile uint64_t sink; /* keeps the compiler from dropping a result */
} job_t;

typedef int (*work_fn)(job_t *job);

typedef ph_error_t (*uint64_fn)(ph_context_t *, uint64_t *);
static const uint64_fn uint64_fns[] = {ph_compute_ahash, ph_compute_dhash, ph_compute_phash,
                                       ph_compute_whash};

static int compute(job_t *job, ph_context_t *ctx) {
    if (job->algo < 4) {
        uint64_t h;
        if (uint64_fns[job->algo](ctx, &h) != PH_SUCCESS)
            return 1;
        job->sink = h;
        return 0;
    }
    ph_digest_t d;
    if (ph_compute_digest(ctx, (ph_algorithm_t)job->algo, &d) != PH_SUCCESS)
        return 1;
    job->sink = d.data[0];
    return 0;
}

static int load_memory(job_t *job, ph_context_t *ctx) {
    return ph_load_from_memory(ctx, job->data, job->length) != PH_SUCCESS;
}

static int w_load_file(job_t *job) {
    return ph_load_from_file(job->ctx, job->path) != PH_SUCCESS;
}

static int w_load_memory(job_t *job) {
    return load_memory(job, job->ctx);
}

static int w_load_pixels(job_t *job) {
    return ph_load_from_pixels(job->ctx, job->data, job->width, job->height, job->channels,
                               0) != PH_SUCCESS;
}

static int w_hash(job_t *job) {
    return compute(job, job->ctx);
}

static int w_load_hash(job_t *job) {
    return load_memory(job, job->ctx) || compute(job, job->ctx);
}

#define UINT64_FLAGS (PH_HASH_AHASH | PH_HASH_DHASH | PH_HASH_PHASH | PH_HASH_WHASH)

static int w_load_multi(job_t *job) {
    uint64_t h[PH_HASH_FLAGS_COUNT];
    if (load_memory(job, job->ctx) || ph_compute_multi(job->ctx, UINT64_FLAGS, h) != PH_SUCCESS)
        return 1;
    job->sink = h[0];
    return 0;
}

static int w_load_separate(job_t *job) {
    if (load_memory(job, job->ctx))
        return 1;
    for (int a = 0; a < 4; a++) {
        uint64_t h;
        if (uint64_fns[a](job->ctx, &h) != PH_SUCCESS)
            return 1;
        job->sink = h;
    }
    return 0;
}

static int w_fresh(job_t *job) {
    ph_context_t *ctx;
    if (ph_create(&ctx) != PH_SUCCESS)
        return 1;
    int bad = ph_load_from_file(ctx, job->path) != PH_SUCCESS || compute(job, ctx);
    ph_free(ctx);
    return bad;
}

static int w_reused(job_t *job) {
    return ph_load_from_file(job->ctx, job->path) != PH_SUCCESS || compute(job, job->ctx);
}

static int w_batch_files(job_t *job) {
    return ph_hash_files(job->items, (size_t)job->n, PH_HASH_PHASH, job->threads) !=
               PH_SUCCESS ||
           job->items[0].status != PH_SUCCESS;
}

static int w_batch_buffers(job_t *job) {
    return ph_hash_buffers(job->buffers, (size_t)job->n, PH_HASH_PHASH, job->threads) !=
               PH_SUCCESS ||
           job->buffers[0].status != PH_SUCCESS;
}

static int w_hamming(job_t *job) {
    uint64_t sum = 0;
    for (int i = 1; i < job->n; i++)
        sum += (uint64_t)ph_hamming_distance(job->hashes[i - 1], job->hashes[i]);
    job->sink = sum;
    return 0;
}

static int w_metric(job_t *job) {
    double sum = 0.0;
    for (int i = 0; i < job->n; i++) {
        switch (job->metric) {
        case 0:
            sum += ph_hamming_distance_digest(&job->a, &job->b);
            break;
        case 1:
            sum += ph_l2_distance(&job->a, &job->b);
            break;
        case 2:
            sum += ph_similarity_digest(&job->a, &job->b);
            break;
        case 3: {
            double pcc;
            if (ph_radial_similarity(&job->a, &job->b, &pcc) != PH_SUCCESS)
                return 1;
            sum += pcc;
            break;
        }
        default: {
            double v;
            if (ph_histogram_intersection(&job->a, &job->b, &v) != PH_SUCCESS)
                return 1;
            sum += v;
        }
        }
    }
    job->sink = (uint64_t)sum;
    return 0;
}

static int w_search(job_t *job) {
    uint64_t query = job->hashes[0] ^ 0x0123456789abcdefULL;
    int best = 65, at = -1;
    for (int i = 0; i < job->n; i++) {
        int d = ph_hamming_distance(query, job->hashes[i]);
        if (d < best) {
            best = d;
            at = i;
        }
    }
    job->sink = (uint64_t)at;
    return 0;
}

static int w_search_all(job_t *job) {
    uint64_t sum = 0;
    for (int i = 0; i < job->n; i++)
        for (int j = i + 1; j < job->n; j++)
            sum += (uint64_t)ph_hamming_distance(job->hashes[i], job->hashes[j]);
    job->sink = sum;
    return 0;
}

/* --- Timing ---------------------------------------------------------------------------- */

static int cmp_double(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

static void time_work(work_fn work, job_t *job, double items, int min_runs, double min_seconds) {
    static double times[MAX_RUNS];
    int runs = 0, repeat = 1;
    /* The warm-up run, which also sets how many times a run repeats the work: enough to
     * last MIN_RUN_SECONDS, so that the clock's resolution and its cost do not show. */
    double t0 = seconds();
    if (work(job)) {
        printf("error the case failed\n");
        return;
    }
    double once = seconds() - t0;
    if (once < MIN_RUN_SECONDS)
        repeat = once > 0 ? (int)(MIN_RUN_SECONDS / once) + 1 : 1000;
    double start = seconds();
    while (runs < MAX_RUNS && (runs < min_runs || seconds() - start < min_seconds)) {
        t0 = seconds();
        for (int r = 0; r < repeat; r++) {
            if (work(job)) {
                printf("error the case failed\n");
                return;
            }
        }
        times[runs++] = (seconds() - t0) / (items * repeat);
    }
    qsort(times, (size_t)runs, sizeof(double), cmp_double);
    printf("{\"min\": %.12g, \"median\": %.12g, \"runs\": %d}\n", times[0], times[runs / 2],
           runs);
}

/* A fixed pseudo-random sequence (xorshift64). */
static uint64_t *random_hashes(int n) {
    uint64_t *h = (uint64_t *)malloc((size_t)n * sizeof(uint64_t));
    uint64_t x = 0x9e3779b97f4a7c15ULL;
    if (!h)
        fail("out of memory", "hashes");
    for (int i = 0; i < n; i++) {
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        h[i] = x;
    }
    return h;
}

static int digest_of(const char *path, int algo, ph_digest_t *out) {
    ph_context_t *ctx;
    if (ph_create(&ctx) != PH_SUCCESS)
        return 1;
    int bad = ph_load_from_file(ctx, path) != PH_SUCCESS ||
              ph_compute_digest(ctx, (ph_algorithm_t)algo, out) != PH_SUCCESS;
    ph_free(ctx);
    return bad;
}

static void run(char *line, int min_runs, double min_seconds) {
    char *f[MAX_FIELDS];
    int n = 0;
    for (char *tok = strtok(line, "\t"); tok && n < MAX_FIELDS; tok = strtok(NULL, "\t"))
        f[n++] = tok;
    if (n == 0)
        fail("an empty case", "");
    const char *name = f[0];
    if (strcmp(name, "build_info") == 0) {
        printf("%s\n", ph_get_build_info());
        return;
    }
    job_t job;
    memset(&job, 0, sizeof job);
    if (ph_create(&job.ctx) != PH_SUCCESS)
        fail("ph_create failed", name);
    work_fn work = NULL;
    double items = 1.0;

#define NEED(count)                                                                           \
    do {                                                                                      \
        if (n != (count) + 1)                                                                 \
            fail("wrong number of fields", name);                                             \
    } while (0)
#define READ(p)                                                                               \
    do {                                                                                      \
        job.path = (p);                                                                       \
        job.data = read_file(job.path, &job.length);                                          \
        if (!job.data)                                                                        \
            fail("cannot read", job.path);                                                    \
    } while (0)

    if (strcmp(name, "load_file") == 0) {
        NEED(1);
        job.path = f[1];
        work = w_load_file;
    } else if (strcmp(name, "load_memory") == 0) {
        NEED(1);
        READ(f[1]);
        work = w_load_memory;
    } else if (strcmp(name, "load_pixels") == 0) {
        NEED(4);
        READ(f[1]);
        job.width = to_int(f[2]);
        job.height = to_int(f[3]);
        job.channels = to_int(f[4]);
        work = w_load_pixels;
    } else if (strcmp(name, "hash") == 0 || strcmp(name, "load_hash") == 0) {
        NEED(2);
        job.algo = to_int(f[1]);
        READ(f[2]);
        if (load_memory(&job, job.ctx))
            fail("cannot load", job.path);
        work = name[0] == 'h' ? w_hash : w_load_hash;
    } else if (strcmp(name, "load_multi") == 0 || strcmp(name, "load_separate") == 0) {
        NEED(1);
        READ(f[1]);
        work = name[5] == 'm' ? w_load_multi : w_load_separate;
    } else if (strcmp(name, "fresh") == 0 || strcmp(name, "reused") == 0) {
        NEED(2);
        job.algo = to_int(f[1]);
        job.path = f[2];
        work = name[0] == 'f' ? w_fresh : w_reused;
    } else if (strcmp(name, "batch_files") == 0 || strcmp(name, "batch_buffers") == 0) {
        NEED(3);
        READ(f[1]);
        job.n = to_int(f[2]);
        job.threads = to_int(f[3]);
        if (name[6] == 'f') {
            job.items = (ph_batch_item_t *)calloc((size_t)job.n, sizeof(ph_batch_item_t));
            if (!job.items)
                fail("out of memory", name);
            for (int i = 0; i < job.n; i++)
                job.items[i].path = job.path;
            work = w_batch_files;
        } else {
            job.buffers =
                (ph_batch_buffer_item_t *)calloc((size_t)job.n, sizeof(ph_batch_buffer_item_t));
            if (!job.buffers)
                fail("out of memory", name);
            for (int i = 0; i < job.n; i++) {
                job.buffers[i].buffer = job.data;
                job.buffers[i].length = job.length;
            }
            work = w_batch_buffers;
        }
        items = job.n;
    } else if (strcmp(name, "hamming") == 0) {
        NEED(1);
        job.n = to_int(f[1]);
        job.hashes = random_hashes(job.n);
        work = w_hamming;
        items = job.n - 1;
    } else if (strcmp(name, "metric") == 0) {
        static const char *const metrics[] = {"hamming", "l2", "similarity", "radial",
                                              "histogram"};
        NEED(4);
        job.metric = -1;
        for (int i = 0; i < 5; i++)
            if (strcmp(f[1], metrics[i]) == 0)
                job.metric = i;
        if (job.metric < 0)
            fail("unknown metric", f[1]);
        job.algo = to_int(f[2]);
        if (digest_of(f[3], job.algo, &job.a) || digest_of(f[4], job.algo, &job.b))
            fail("cannot hash", f[3]);
        job.n = 1000;
        work = w_metric;
        items = job.n;
    } else if (strcmp(name, "search") == 0 || strcmp(name, "search_all") == 0) {
        NEED(1);
        job.n = to_int(f[1]);
        job.hashes = random_hashes(job.n);
        if (strcmp(name, "search") == 0) {
            work = w_search;
            items = job.n;
        } else {
            work = w_search_all;
            items = (double)job.n * (job.n - 1) / 2.0;
        }
    } else {
        fail("unknown case", name);
    }

    time_work(work, &job, items, min_runs, min_seconds);
    fflush(stdout);
    ph_free(job.ctx);
    free(job.data);
    free(job.items);
    free(job.buffers);
    free(job.hashes);
}

int main(int argc, char **argv) {
    static char line[MAX_LINE];
    if (argc != 3)
        fail("usage", "bench <min_runs> <min_seconds>");
    int min_runs = to_int(argv[1]);
    double min_seconds = strtod(argv[2], NULL);
    while (fgets(line, sizeof line, stdin)) {
        line[strcspn(line, "\r\n")] = '\0';
        if (line[0] != '\0')
            run(line, min_runs, min_seconds);
    }
    return 0;
}
