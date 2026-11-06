/*
 * sshole-crypt-probe.c
 *
 * Shows what crypt(3) returns for long passwords, and what OpenSSH's non-PAM
 * password check would do with that result before and after the 10.6p2 fix.
 *
 * Build against musl:   musl-gcc -static -O1 -o probe-musl sshole-crypt-probe.c
 * Build against glibc:  gcc -O1 -o probe-glibc sshole-crypt-probe.c -lcrypt
 * Run:                  ./probe-musl
 *
 * The password-check functions below are a re-typing of the comparison logic in
 * sys_auth_passwd() (auth-passwd.c) from OpenSSH portable, before commit
 * 4353fdc43e and after it. They are NOT the OpenSSH code itself: no sshd is
 * built, started or contacted. This program opens no sockets and reads or
 * writes no files.
 */
#include <crypt.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MIN_PASSWORD_HASH_LEN 4 /* added by the fix */

/*
 * stored:   the password field of the account ("*" for key-only accounts)
 * borrowed: the salt xcrypt()'s pick_salt() would take from some other account
 *           ("$6$...$" if any account has a SHA-512 hash, otherwise "xx")
 * fixed:    apply the length check added in 10.6p2
 */
static int check(const char *stored, const char *borrowed, const char *pw, int fixed)
{
	const char *salt = NULL;
	char *enc;

	if (stored[0] && stored[1]) /* valid user with a real-looking field */
		salt = stored;
	if (salt == NULL)
		salt = borrowed; /* xcrypt(password, NULL) picks one */
	enc = crypt(pw, salt);
	if (fixed && strlen(stored) < MIN_PASSWORD_HASH_LEN)
		return 0;
	return enc != NULL && strcmp(enc, stored) == 0;
}

static char *repeat(size_t n)
{
	char *s = malloc(n + 1);
	memset(s, 'A', n);
	s[n] = 0;
	return s;
}

static const char *describe(const char *r, char *buf, size_t bl)
{
	if (r == NULL)
		return "NULL";
	if (strlen(r) <= 3)
		snprintf(buf, bl, "\"%s\" (not a hash)", r);
	else
		snprintf(buf, bl, "hash, %zu chars, starts %.4s", strlen(r), r);
	return buf;
}

int main(void)
{
	static const size_t lens[] = {8, 72, 255, 256, 257, 300, 1024};
	struct {
		const char *name;
		const char *setting;
	} kinds[] = {
	    {"DES    (salt xx)", "xx"},
	    {"MD5    ($1$)", "$1$abcdefgh$"},
	    {"bcrypt ($2b$)", "$2b$04$abcdefghijklmnopqrstuu"},
	    {"SHA-256($5$)", "$5$abcdefgh$"},
	    {"SHA-512($6$)", "$6$abcdefgh$"},
	};
	char buf[96];
	size_t i, k;

	puts("== Part 1: what crypt() returns for a password of N bytes ==");
	printf("%-16s", "scheme");
	for (i = 0; i < sizeof lens / sizeof *lens; i++)
		printf(" | %-9zu", lens[i]);
	puts("");
	for (k = 0; k < sizeof kinds / sizeof *kinds; k++) {
		printf("%-16s", kinds[k].name);
		for (i = 0; i < sizeof lens / sizeof *lens; i++) {
			char *pw = repeat(lens[i]);
			const char *r = crypt(pw, kinds[k].setting);
			const char *d = r == NULL ? "NULL" : (strlen(r) <= 3 ? r : "hash");
			printf(" | %-9s", d);
			free(pw);
		}
		puts("");
	}

	puts("\n== Part 2: exact failure value for SHA-512 at 257 bytes ==");
	{
		char *pw = repeat(257);
		const char *r = crypt(pw, "$6$abcdefgh$");
		printf("crypt(257 x 'A', \"$6$abcdefgh$\") -> %s\n", describe(r, buf, sizeof buf));
		free(pw);
	}

	puts("\n== Part 3: would sshd's non-PAM password check accept it? ==");
	puts("(a password of N 'A' bytes, never the real password; \"old\" = before 10.6p2, \"new\" = after)");
	{
		const char *stores[] = {"*", "!", "x", "!!", "*LOCKED*", "!$6$abcdefgh$zzzz"};
		const char *borrowed[] = {"$6$abcdefgh$", "xx"};
		static const size_t tl[] = {8, 256, 257, 1024};
		size_t s, b, t;
		printf("%-20s %-14s", "stored field", "borrowed salt");
		for (t = 0; t < 4; t++)
			printf(" | %-5zu old/new", tl[t]);
		puts("");
		for (s = 0; s < sizeof stores / sizeof *stores; s++) {
			for (b = 0; b < 2; b++) {
				printf("%-20s %-14s", stores[s], borrowed[b]);
				for (t = 0; t < 4; t++) {
					char *pw = repeat(tl[t]);
					printf(" | %-5s %d/%d  ", "", check(stores[s], borrowed[b], pw, 0),
					       check(stores[s], borrowed[b], pw, 1));
					free(pw);
				}
				puts("");
			}
		}
	}
	return 0;
}
