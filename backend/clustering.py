"""Small deterministic DBSCAN implementation for the SQLite teaching application.

Neighborhoods include the point itself; label -1 is noise. Serving uses versioned
assignments only, without inventing a DBSCAN predict operation.
"""

import math
from collections import deque
from dataclasses import dataclass

Vector = tuple[float, ...]


@dataclass(frozen=True)
class Scaler:
    means: Vector
    scales: Vector

    @classmethod
    def fit(cls, rows: tuple[Vector, ...]) -> 'Scaler':
        if not rows or any(len(r)!=len(rows[0]) for r in rows):
            raise ValueError('Training vectors must be nonempty and have matching dimensions')
        means = tuple(sum(r[i] for r in rows)/len(rows) for i in range(len(rows[0])))
        scales = tuple(math.sqrt(sum((r[i]-means[i])**2 for r in rows)/len(rows)) or 1.0 for i in range(len(means)))
        return cls(means,scales)

    def transform(self, row: Vector) -> Vector:
        if len(row)!=len(self.means):
            raise ValueError('Feature schema does not match the training scaler')
        return tuple((v-m)/s for v,m,s in zip(row,self.means,self.scales))


def distance(left: Vector, right: Vector) -> float:
    return math.sqrt(sum((a-b)**2 for a,b in zip(left,right,strict=True)))


def dbscan(rows: tuple[Vector, ...], eps: float, min_samples: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if eps<=0 or min_samples<2:
        raise ValueError('DBSCAN requires positive eps and min_samples >= 2')
    if any(not r or len(r)!=len(rows[0]) or not all(math.isfinite(v) for v in r) for r in rows):
        raise ValueError('Features must have matching dimensions and finite values')
    neighbors = tuple(tuple(j for j,other in enumerate(rows) if distance(row,other)<=eps) for row in rows)
    core = tuple(i for i,n in enumerate(neighbors) if len(n)>=min_samples)
    core_set = set(core)
    labels = [-1]*len(rows)
    visited: set[int] = set()
    cluster = 0
    for point in range(len(rows)):
        if point in visited:
            continue
        visited.add(point)
        if point not in core_set:
            continue
        labels[point] = cluster
        queue = deque(neighbors[point])
        queued = set(neighbors[point])
        while queue:
            candidate = queue.popleft()
            if candidate not in visited:
                visited.add(candidate)
                if candidate in core_set:
                    for neighbor in neighbors[candidate]:
                        if neighbor not in queued:
                            queued.add(neighbor)
                            queue.append(neighbor)
            if labels[candidate]==-1:
                labels[candidate] = cluster
        cluster += 1
    return tuple(labels),core


def pair_agreement(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    comparisons = [(left[i]>=0 and left[i]==left[j]) == (right[i]>=0 and right[i]==right[j])
                   for i in range(len(left)) for j in range(i+1,len(left))]
    return sum(comparisons)/len(comparisons) if comparisons else 0.0
