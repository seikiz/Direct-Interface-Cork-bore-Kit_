package com.dick.core

import java.security.MessageDigest

/**
 * PyRandom —— 与 CPython `random.Random` **逐位相同**的伪随机数发生器。
 *
 * 为什么非要对齐到这个程度
 * ------------------------
 * 生活层的菜单是**确定性抽样**，种子 = `角色｜世界第几天｜哪一餐`
 * （`life_core.sample_meal`）。这条设计的承诺是："重启、回档、**电脑端和手机端**算出来都一样"。
 * 手机端如果换一个随机数发生器，同一个角色同一顿饭在两端就是两道菜 —— 承诺当场作废，
 * 而且这种漂很难被发现（不会报错，只是"她今天吃的东西不一样了"）。
 *
 * 所以这里把 CPython 的三件事都复刻了：
 *   ① `Random(seed_str)` 的种子转换：`int.from_bytes(s.encode() + sha512(s.encode()), "big")`
 *   ② MT19937 的 `init_by_array`（不是 `init_genrand` —— 整数种子走的是前半段）
 *   ③ 抽样用到的三个出口：`getrandbits(k)` / `random()` / `randrange(n)`
 *
 * 验证方式：`selftest/LifeParityTest.kt` 拿电脑端算出来的菜单逐字比对（见 `tools/gen_parity.py`）。
 */
class PyRandom private constructor() {

    private val mt = IntArray(N)
    private var index = N + 1

    companion object {
        private const val N = 624
        private const val M = 397
        private const val UPPER_MASK = -0x80000000      // 0x80000000
        private const val LOWER_MASK = 0x7fffffff
        private const val MAG01_1 = -0x66f74f21         // 0x9908b0df

        /** `random.Random("阿绫|739000|breakfast")` 的等价物。 */
        fun fromString(seed: String): PyRandom {
            val r = PyRandom()
            r.seedFromString(seed)
            return r
        }

        /** `random.Random(整数)`（与字符串种子那条路不同：直接进 init_by_array）。 */
        fun fromInt(seed: Long): PyRandom {
            val r = PyRandom()
            val words = ArrayList<Int>()
            var v = Math.abs(seed)
            if (v == 0L) words.add(0) else while (v != 0L) {
                words.add((v and 0xffffffffL).toInt())
                v = v ushr 32
            }
            r.initByArray(words.toIntArray())
            return r
        }
    }

    private fun seedFromString(seed: String) {
        val payload = seed.toByteArray(Charsets.UTF_8)
        val digest = MessageDigest.getInstance("SHA-512").digest(payload)
        val all = ByteArray(payload.size + digest.size)
        System.arraycopy(payload, 0, all, 0, payload.size)
        System.arraycopy(digest, 0, all, payload.size, digest.size)
        // int.from_bytes(all, "big<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌") → 去掉前导 0，再按 32 位一组取出。
        // 注意顺序：CPython 的 key 数组是**低位在前**（`n >> (32*i)`），
        // 所以从左边切出来的字节块要反过来放 —— 这一处搞错，两端就吃不到同一份菜单
        // （而且是那种不会报错、只是"她今天吃的东西不一样"的漂）。
        var start = 0
        while (start < all.size && all[start].toInt() == 0) start++
        val body = if (start >= all.size) byteArrayOf(0) else all.copyOfRange(start, all.size)
        val pad = (4 - body.size % 4) % 4
        val padded = ByteArray(pad + body.size)
        System.arraycopy(body, 0, padded, pad, body.size)
        val beWords = IntArray(padded.size / 4)
        for (i in beWords.indices) {
            val o = i * 4
            beWords[i] = ((padded[o].toInt() and 0xFF) shl 24) or
                    ((padded[o + 1].toInt() and 0xFF) shl 16) or
                    ((padded[o + 2].toInt() and 0xFF) shl 8) or
                    (padded[o + 3].toInt() and 0xFF)
        }
        initByArray(beWords.reversedArray())
    }

    private fun initGenrand(s: Int) {
        mt[0] = s
        for (m in 1 until N) {
            mt[m] = 1812433253 * (mt[m - 1] xor (mt[m - 1] ushr 30)) + m
        }
        index = N
    }

    private fun initByArray(key: IntArray) {
        initGenrand(19650218)
        val keyLength = key.size
        var i = 1
        var j = 0
        var k = if (N > keyLength) N else keyLength
        while (k > 0) {
            mt[i] = (mt[i] xor ((mt[i - 1] xor (mt[i - 1] ushr 30)) * 1664525)) + key[j] + j
            i++
            j++
            if (i >= N) {
                mt[0] = mt[N - 1]
                i = 1
            }
            if (j >= keyLength) j = 0
            k--
        }
        k = N - 1
        while (k > 0) {
            mt[i] = (mt[i] xor ((mt[i - 1] xor (mt[i - 1] ushr 30)) * 1566083941)) - i
            i++
            if (i >= N) {
                mt[0] = mt[N - 1]
                i = 1
            }
            k--
        }
        mt[0] = -0x80000000      // 0x80000000
    }

    /** MT19937 的一个 32 位输出（`genrand_uint32`）。 */
    fun nextUInt32(): Int {
        var y: Int
        if (index >= N) {
            var kk = 0
            while (kk < N - M) {
                y = (mt[kk] and UPPER_MASK) or (mt[kk + 1] and LOWER_MASK)
                mt[kk] = mt[kk + M] xor (y ushr 1) xor (if (y and 1 != 0) MAG01_1 else 0)
                kk++
            }
            while (kk < N - 1) {
                y = (mt[kk] and UPPER_MASK) or (mt[kk + 1] and LOWER_MASK)
                mt[kk] = mt[kk + (M - N)] xor (y ushr 1) xor (if (y and 1 != 0) MAG01_1 else 0)
                kk++
            }
            y = (mt[N - 1] and UPPER_MASK) or (mt[0] and LOWER_MASK)
            mt[N - 1] = mt[M - 1] xor (y ushr 1) xor (if (y and 1 != 0) MAG01_1 else 0)
            index = 0
        }
        y = mt[index]
        index++
        y = y xor (y ushr 11)
        y = y xor ((y shl 7) and -0x62d3a980)      // 0x9d2c5680
        y = y xor ((y shl 15) and -0x103a0000)     // 0xefc60000
        y = y xor (y ushr 18)
        return y
    }

    /** `random.random()`（genrand_res53：两段拼出来的 53 位小数）。 */
    fun nextDouble(): Double {
        val a = nextUInt32() ushr 5
        val b = nextUInt32() ushr 6
        return (a * 67108864.0 + b) * (1.0 / 9007199254740992.0)
    }

    /** `getrandbits(k)`（k ≤ 32 的快路径；抽样只用得到这一段）。 */
    fun getRandBits(k: Int): Int {
        if (k <= 0) return 0
        if (k <= 32) return nextUInt32() ushr (32 - k)
        // 超过 32 位：按 CPython 的写法拼出来（我们用不到，但不能悄悄给错）
        var result = 0L
        var got = 0
        while (got < k) {
            val take = if (k - got > 32) 32 else k - got
            val word = nextUInt32() ushr (32 - take)
            result = result or (word.toLong() shl got)
            got += take
        }
        return result.toInt()
    }

    /** `randrange(n)`（n > 0）：CPython 的 `_randbelow_with_getrandbits`。 */
    fun randRange(n: Int): Int {
        if (n <= 0) throw IllegalArgumentException("randrange 的参数必须为正：$n")
        val k = 32 - Integer.numberOfLeadingZeros(n)
        var r = getRandBits(k)
        while (r >= n) r = getRandBits(k)
        return r
    }

    fun <T> pick(pool: List<T>): T? = if (pool.isEmpty()) null else pool[randRange(pool.size)]
}
