import numpy as np

from .src.decompose_4x4 import decompose_4x4_optimal
from .src.gate import GateFC, GateSingle
from .src.optimize import optimize_gates
from .src.two_level_unitary import TwoLevelUnitary
from .src.utils import PAULI_X, is_unitary, is_special_unitary, is_power_of_two


def two_level_decompose(A):
    """Returns list of two-level unitary matrices, which multiply to A.

    Matrices are listed in application order, i.e. if aswer is [u_1, u_2, u_3],
    it means A = u_3 u_2 u_1.

    :param A: matrix to decompose.
    :return: The decomposition - list of two-level unitary matrices.
    """

    def make_eliminating_matrix(a, b):
        """Returns unitary matrix U, s.t. [a, b] U = [c, 0].

        Makes second element equal to zero.
        """
        assert (np.abs(a) > 1e-9 and np.abs(b) > 1e-9)
        theta = np.arctan(np.abs(b / a))
        lmbda = -np.angle(a)
        mu = np.pi + np.angle(b) - np.angle(a) - lmbda
        result = np.array([[np.cos(theta) * np.exp(1j * lmbda),
                            np.sin(theta) * np.exp(1j * mu)],
                           [-np.sin(theta) * np.exp(-1j * mu),
                            np.cos(theta) * np.exp(-1j * lmbda)]])
        assert is_special_unitary(result)
        assert np.allclose(np.angle(result[0, 0] * a + result[1, 0] * b), 0)
        assert (np.abs(result[0, 1] * a + result[1, 1] * b) < 1e-9)
        return result

    assert is_unitary(A)
    n = A.shape[0]
    result = []
    # Make a copy, because we are going to mutate it.
    current_A = np.array(A)

    for i in range(n - 2):
        for j in range(n - 1, i, -1):
            if abs(current_A[i, j]) < 1e-9:
                # Element is already zero, skipping.
                pass
            else:
                if abs(current_A[i, j - 1]) < 1e-9:
                    # Just swap columns.
                    u_2x2 = PAULI_X
                else:
                    u_2x2 = make_eliminating_matrix(
                        current_A[i, j - 1], current_A[i, j])
                u_2x2 = TwoLevelUnitary(u_2x2, n, j - 1, j)
                u_2x2.multiply_right(current_A)
                result.append(u_2x2.inv())

    result.append(TwoLevelUnitary(
        current_A[n - 2:n, n - 2:n], n, n - 2, n - 1))
    return result


def two_level_decompose_gray(A):
    """Returns list of two-level matrices, which multiply to A.

    :param A: matrix to decompose.
    :return: The decomposition - list of two-level unitary matrices. Guarantees
      that each matrix acts on single bit.
    """
    N = A.shape[0]
    assert is_power_of_two(N)
    assert A.shape == (N, N), "Matrix must be square."
    assert is_unitary(A)

    # Build permutation matrix.
    perm = [x ^ (x // 2) for x in range(N)]  # Gray code.
    P = np.zeros((N, N), dtype=np.complex128)
    for i in range(N):
        P[i][perm[i]] = 1

    result = two_level_decompose(P @ A @ P.T)
    for matrix in result:
        matrix.apply_permutation(perm)
    return result


def matrix_to_gates(A, **kwargs):
    """Given unitary matrix A, retuns sequence of gates which implements
    action of this matrix on register of qubits.

    If optimized=True, applies optimized algorithm yielding less gates. Will
    affect output only when A is 4x4 matrix.

    :param A: 2^N x 2^N unitary matrix.
    :return: sequence of `Gate`s.
    """
    if 'optimize' in kwargs and kwargs['optimize'] and A.shape[0] == 4:
        return decompose_4x4_optimal(A)

    matrices = two_level_decompose_gray(A)
    gates = sum([matrix.to_fc_gates() for matrix in matrices], [])
    gates = optimize_gates(gates)
    return gates


def matrix_to_qsharp(matrix, **kwargs):
    """Given unitary matrix A, retuns Q# code which implements
    action of this matrix on register of qubits called `qs`.

    :param matrix: 2^N x 2^N unitary matrix to convert to Q# code.
    :param op_name: name which operation should have. Default name is
      "ApplyUnitaryMatrix".
    :return: string - Q# code.
    """
    op_name = 'ApplyUnitaryMatrix'
    if 'op_name' in kwargs:
        op_name = kwargs['op_name']
    header = ('operation %s (qs : Qubit[]) : Unit {\n' % op_name)
    footer = '}\n'
    code = '\n'.join(['  ' + gate.to_qsharp_command()
                      for gate in matrix_to_gates(matrix, **kwargs)])
    return header + code + '\n' + footer


def matrix_to_cirq_circuit(A, **kwargs):
    """Converts unitary matrix to Cirq circuit.

    :param A: 2^N x 2^N unitary matrix.
    :return: `cirq.Circuit` implementing this matrix.
    """
    import cirq

    def gate_to_cirq(gate2):
        if gate2.name == 'X':
            return cirq.X
        elif gate2.name == 'Ry':
            return cirq.ry(-gate2.arg)
        elif gate2.name == 'Rz':
            return cirq.rz(-gate2.arg)
        elif gate2.name == 'R1':
            return cirq.ZPowGate(exponent=gate2.arg / np.pi)
        else:
            raise RuntimeError("Can't implement: %s" % gate2)

    gates = matrix_to_gates(A, **kwargs)
    qubits_count = int(np.log2(A.shape[0]))
    circuit = cirq.Circuit()
    qubits = cirq.LineQubit.range(qubits_count)[::-1]

    for gate in gates:
        if isinstance(gate, GateFC):
            controls = [qubits[i]
                        for i in range(qubits_count) if i != gate.qubit_id]
            target = qubits[gate.qubit_id]
            arg_gates = controls + [target]
            cgate = cirq.ControlledGate(
                gate_to_cirq(gate.gate2),
                num_controls=qubits_count - 1)
            circuit.append(cgate.on(*arg_gates))
        elif isinstance(gate, GateSingle):
            circuit.append(gate_to_cirq(gate.gate2).on(qubits[gate.qubit_id]))
        else:
            raise RuntimeError('Unknown gate type.')
    return circuit


def matrix_to_qiskit_circuit(A, **kwargs):
    """Converts unitary matrix to Qiskit circuit.

    :param A: 2^N x 2^N unitary matrix.
    :return: `qiskit.QuantumCircuit` implementing this matrix.
    """
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import XGate, RYGate, RZGate, U1Gate

    def gate_to_qiskit(gate2):
        if gate2.name == 'X':
            return XGate()
        elif gate2.name == 'Ry':
            return RYGate(-gate2.arg)
        elif gate2.name == 'Rz':
            return RZGate(-gate2.arg)
        elif gate2.name == 'R1':
            return U1Gate(gate2.arg)
        else:
            raise RuntimeError("Can't implement: %s" % gate2)

    gates = matrix_to_gates(A, **kwargs)
    qubits_count = int(np.log2(A.shape[0]))
    circuit = QuantumCircuit(qubits_count)
    qubits = circuit.qubits

    for gate in gates:
        if isinstance(gate, GateFC):
            controls = [qubits[i]
                        for i in range(qubits_count) if i != gate.qubit_id]
            target = qubits[gate.qubit_id]
            arg_gates = controls + [target]
            cgate = gate_to_qiskit(gate.gate2)
            if len(controls):
                cgate = cgate.control(num_ctrl_qubits=len(controls))
            circuit.append(cgate, arg_gates)
        elif isinstance(gate, GateSingle):
            circuit.append(gate_to_qiskit(gate.gate2), [qubits[gate.qubit_id]])
        else:
            raise RuntimeError('Unknown gate type.')
    return circuit
