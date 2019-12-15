import numpy as np

from src.gate2 import Gate2
from src.two_level_unitary import TwoLevelUnitary



class Gate:
    """Represents gate acting on register of qubits."""
    pass


class GateSingle(Gate):
    """Represents gate acting on a single qubit in a register."""

    def __init__(self, gate2, qubit_id, qubit_count):
        self.gate2 = gate2
        self.qubit_id = qubit_id
        self.qubit_count = qubit_count

    def to_qsharp_command(self):
        if self.gate2.name in ('Rx', 'Ry', 'Rz'):
            # QSharp uses different sign.
            return '%s(%.15f, qs[%d]);' % (
                self.gate2.name, -self.gate2.arg, self.qubit_id)
        elif self.gate2.name == 'R1':
            return 'R1(%.15f, qs[%d]);' % (self.gate2.arg, self.qubit_id)
        elif self.gate2.name == 'X':
            return 'X(qs[%d]);' % (self.qubit_id)

    def to_matrix(self):
        """Tensor product I x I x ... x `gate2.to_matrix()` x I x ... x I."""
        matrix = self.gate2.to_matrix()
        tile_size = 2**(self.qubit_id + 1)

        if (self.qubit_id == 0):
            tile = matrix
        else:
            tile = np.zeros((tile_size, tile_size), dtype=np.complex128)
            subtile = np.eye(tile_size // 2)
            for i in range(2):
                for j in range(2):
                    tile[i * (tile_size // 2):(i + 1) * (tile_size // 2), j *
                         (tile_size // 2):(j + 1) * (tile_size // 2)] = subtile * matrix[i, j]

        matrix_size = 2 ** self.qubit_count
        ret = np.zeros((matrix_size, matrix_size), dtype=np.complex128)
        for i in range(2**(self.qubit_count - self.qubit_id - 1)):
            ret[i * tile_size:(i + 1) * tile_size,
                i * tile_size:(i + 1) * tile_size] = tile

        return ret

    def __repr__(self):
        return str(self.gate2) + " on bit " + str(self.qubit_id)

    def type(self):
        return self.gate2.name + "-single"


class GateFC(Gate):
    """ Represents fully contolled gate.

    `flip_mask` has ones at positions, for which qubit should be flipped before and after
    applying operation.
    """

    def __init__(self, gate2, qubit_id, qubit_count, flip_mask=0):
        self.gate2 = gate2
        self.qubit_id = qubit_id
        self.flip_mask = flip_mask
        self.qubit_count = qubit_count

    def without_flips(self):
        return GateFC(self.gate2, self.qubit_id, self.qubit_count, flip_mask=0)

    def to_qsharp_command(self):
        # On one qubit controlled gate is just single-qubit gate.
        if self.qubit_count == 1:
            return GateSingle(self.gate2, self.qubit_id, 1).to_qsharp_command()

        if self.flip_mask != 0:
            raise ValueError("flip_mask must be zero.")

        controls = [i for i in range(self.qubit_count) if i != self.qubit_id]
        controls = '[' + ', '.join(['qs[%d]' % i for i in controls]) + ']'
        if self.gate2.name in ('Rx', 'Ry', 'Rz'):
            # QSharp uses different sign.
            return 'Controlled %s(%s, (%.15f, qs[%d]));' % (
                self.gate2.name, controls, -self.gate2.arg, self.qubit_id)
        elif self.gate2.name == 'R1':
            return 'Controlled R1(%s, (%.15f, qs[%d]));' % (
                controls, self.gate2.arg, self.qubit_id)
        elif self.gate2.name == 'X':
            return 'Controlled X(%s, (qs[%d]));' % (controls, self.qubit_id)

    def to_matrix(self):
        matrix_size = 2**self.qubit_count
        index2 = (matrix_size - 1) - self.flip_mask
        index1 = index2 - 2**self.qubit_id
        matrix = TwoLevelUnitary(
            self.gate2.to_matrix(),
            matrix_size,
            index1,
            index2)
        return matrix.get_full_matrix()

    def __repr__(self):
        return "%s on bit %d, fully controlled" % (
            str(self.gate2), self.qubit_id)

    def type(self):
        return self.gate2.name + "-FC"