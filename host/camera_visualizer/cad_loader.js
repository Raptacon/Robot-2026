/**
 * CAD model loader for the robot camera visualizer.
 *
 * Loads GLTF/GLB models, provides transparency control,
 * click-to-select with bounding box and transform output.
 */

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import * as BufferGeometryUtils from 'three/addons/utils/BufferGeometryUtils.js';

export class CadModelManager {
  constructor(scene, modelParent = null) {
    this.scene = scene;
    this.modelParent = modelParent || scene;  // where model gets added (robotGroup or scene)
    this.model = null;            // THREE.Group — loaded GLTF scene root
    this.meshes = [];             // [{ mesh, originalColor, visible }]
    this.partTree = [];           // [{ name, children: [...], meshName }]
    this.opacity = 0.5;
    this.selectedMesh = null;
    this.selectionBox = null;     // THREE.BoxHelper
    this.showBBox = true;
    this.onSelect = null;         // callback(info) where info = { name, center, size, point }
    this.onStatusChange = null;   // callback(statusText)
    this._hideStack = [];         // undo stack: names hidden in order
    this._redoStack = [];         // redo stack
    this._highlightedMeshes = []; // multi-mesh highlight for assemblies
    this._loader = new GLTFLoader();
    // Draco decoder for compressed GLTF (e.g. Onshape exports)
    const dracoLoader = new DRACOLoader();
    dracoLoader.setDecoderPath(
      'https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/libs/draco/'
    );
    this._loader.setDRACOLoader(dracoLoader);
    this._appliedScale = 1.0;
  }

  // ── Loading ──────────────────────────────────────────────────────

  async loadUrl(url) {
    const name = url.split('/').pop();
    this._setStatus(`Loading ${name}...`);
    return new Promise((resolve, reject) => {
      this._loader.load(
        url,
        (gltf) => {
          this._setStatus(`Processing ${name}...`);
          // Defer to let the status update render
          setTimeout(() => {
            this._onGltfLoaded(gltf);
            resolve();
          }, 50);
        },
        (progress) => {
          if (progress.total > 0) {
            const pct = Math.round((progress.loaded / progress.total) * 100);
            this._setStatus(`Loading ${name}... ${pct}%`);
          } else {
            const mb = (progress.loaded / 1024 / 1024).toFixed(1);
            this._setStatus(`Loading ${name}... ${mb} MB`);
          }
        },
        (err) => {
          this._setStatus(`Error: ${err.message || err}`);
          reject(err);
        },
      );
    });
  }

  async loadFile(file) {
    this._setStatus(`Loading ${file.name}...`);
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = async (e) => {
        try {
          const gltf = await this._loader.parseAsync(
            e.target.result, ''
          );
          this._onGltfLoaded(gltf);
          resolve();
        } catch (err) {
          this._setStatus(`Error: ${err.message}`);
          reject(err);
        }
      };
      reader.onerror = () => {
        this._setStatus('Error reading file');
        reject(reader.error);
      };
      reader.readAsArrayBuffer(file);
    });
  }

  _onGltfLoaded(gltf) {
    this.unload();

    const root = gltf.scene;

    // Measure raw bounding box before any transforms
    const rawBox = new THREE.Box3().setFromObject(root);
    const rawSize = rawBox.getSize(new THREE.Vector3());
    const rawCenter = rawBox.getCenter(new THREE.Vector3());
    const maxDim = Math.max(rawSize.x, rawSize.y, rawSize.z);
    console.log(`[CAD] Raw bounding box: size=(${rawSize.x.toFixed(3)}, ${rawSize.y.toFixed(3)}, ${rawSize.z.toFixed(3)}) center=(${rawCenter.x.toFixed(3)}, ${rawCenter.y.toFixed(3)}, ${rawCenter.z.toFixed(3)}) maxDim=${maxDim.toFixed(3)}`);

    // Auto-detect units based on size
    // A typical FRC robot is ~0.6-1.0m. With bumpers/mechanisms up to ~2m.
    // If maxDim > 20, likely inches (24" = 0.6m robot reads as 24).
    // If maxDim > 200, likely millimeters (600mm = 0.6m robot reads as 600).
    let unitNote = 'meters';
    if (maxDim > 200) {
      this._appliedScale = 0.001;
      root.scale.set(0.001, 0.001, 0.001);
      unitNote = 'mm→meters';
    } else if (maxDim > 20) {
      this._appliedScale = 0.0254;
      root.scale.set(0.0254, 0.0254, 0.0254);
      unitNote = 'inches→meters';
    } else {
      this._appliedScale = 1.0;
    }

    // X rotation to convert coordinate systems, adjustable with Flip button.
    // 0=none, 1=+90°, 2=180°, 3=-90° around X
    this._xSteps = 1;  // 90° X — correct for Onshape GLTF exports
    this._yawSteps = 2; // 180° yaw — Onshape exports are rear-facing by default
    this.model = root;  // set before _applyOrientation so it doesn't bail
    this._applyOrientation();
    this.modelParent.add(root);

    // Log final bounding box for debugging
    root.updateMatrixWorld(true);
    const finalBox = new THREE.Box3().setFromObject(root);
    const finalSize = finalBox.getSize(new THREE.Vector3());
    const finalCenter = finalBox.getCenter(new THREE.Vector3());
    console.log(`[CAD] Final bounding box: size=(${finalSize.x.toFixed(4)}, ${finalSize.y.toFixed(4)}, ${finalSize.z.toFixed(4)}) center=(${finalCenter.x.toFixed(4)}, ${finalCenter.y.toFixed(4)}, ${finalCenter.z.toFixed(4)})`);

    // Count meshes for status
    let meshCount = 0;
    root.traverse((obj) => { if (obj.isMesh) meshCount++; });

    this._setStatus(`${meshCount} parts (${unitNote})`);

    // Optimization: merge all primitives per named parent node into single
    // meshes. Onshape exports create thousands of draw calls (16K+) from
    // multi-primitive meshes. Merging reduces draw calls to ~100-200.
    this.meshes = [];
    this._optimizeModel(root);
  }

  // ── Model optimization ────────────────────────────────────────────

  _optimizeModel(root) {
    // Group meshes by their nearest named parent (not top-level).
    // This preserves per-part colors and selection while merging the 16K
    // primitives into ~100-200 draw calls.
    //
    // Also build a hierarchy tree for the UI overlay.

    this.partTree = [];
    const groups = new Map(); // groupName -> { geometries, colors }

    // Step 1: Build tree and collect mesh geometries
    const self = this;
    function processNode(node, parentTreeNode) {
      const name = node.name || '';
      const isNamed = name && !name.startsWith('Scene') &&
                      !name.startsWith('mesh') && !name.startsWith('Object');

      let treeNode = null;
      if (isNamed) {
        treeNode = { name, children: [], visible: true };
        if (parentTreeNode) {
          parentTreeNode.children.push(treeNode);
        } else {
          self.partTree.push(treeNode);
        }
      }

      if (node.isMesh) {
        const color = node.material.color ? node.material.color.getHex() : 0x888888;

        // Find nearest named ancestor for grouping
        let groupName = '__unnamed__';
        let p = node;
        while (p && p !== root) {
          if (p.name && !p.name.startsWith('Scene') &&
              !p.name.startsWith('mesh') && !p.name.startsWith('Object')) {
            groupName = p.name;
            break;
          }
          p = p.parent;
        }

        node.updateWorldMatrix(true, false);
        const geo = node.geometry.clone();
        geo.applyMatrix4(node.matrixWorld);
        const keepAttrs = ['position', 'normal'];
        for (const attr of Object.keys(geo.attributes)) {
          if (!keepAttrs.includes(attr)) geo.deleteAttribute(attr);
        }

        if (!groups.has(groupName)) groups.set(groupName, { geometries: [], colors: [] });
        groups.get(groupName).geometries.push(geo);
        groups.get(groupName).colors.push(color);

        node.material.dispose();
      }

      for (const child of (node.children || [])) {
        processNode(child, treeNode || parentTreeNode);
      }
    }

    for (const child of root.children.slice()) {
      processNode(child, null);
    }

    // Step 2: Clear original children
    while (root.children.length) root.remove(root.children[0]);

    // Step 3: Merge each named group into a single mesh
    let totalDrawCalls = 0;
    root.updateWorldMatrix(true, false);
    const invRoot = root.matrixWorld.clone().invert();

    for (const [name, { geometries, colors }] of groups) {
      // Most common color in this group
      const colorCounts = new Map();
      colors.forEach(c => colorCounts.set(c, (colorCounts.get(c) || 0) + 1));
      let bestColor = 0x888888, bestCount = 0;
      for (const [c, n] of colorCounts) {
        if (n > bestCount) { bestColor = c; bestCount = n; }
      }

      try {
        const merged = BufferGeometryUtils.mergeGeometries(geometries, false);
        if (!merged) continue;

        const mat = new THREE.MeshPhongMaterial({
          color: bestColor, transparent: true, opacity: this.opacity,
          depthWrite: true, side: THREE.DoubleSide,
        });
        const mesh = new THREE.Mesh(merged, mat);
        mesh.name = name;
        mesh.applyMatrix4(invRoot);
        root.add(mesh);
        this.meshes.push({ mesh, originalColor: bestColor, visible: true });
        totalDrawCalls++;
      } catch (e) {
        // Fallback: add individually
        geometries.forEach((geometry, i) => {
          const mat = new THREE.MeshPhongMaterial({
            color: colors[i] || 0x888888, transparent: true, opacity: this.opacity,
            depthWrite: true, side: THREE.DoubleSide,
          });
          const mesh = new THREE.Mesh(geometry, mat);
          mesh.name = name;
          mesh.applyMatrix4(invRoot);
          root.add(mesh);
          this.meshes.push({ mesh, originalColor: colors[i] || 0x888888, visible: true });
          totalDrawCalls++;
        });
      }

      geometries.forEach(g => g.dispose());
    }

    console.log(`[CAD] Optimized: ${groups.size} named parts → ${totalDrawCalls} draw calls`);
    console.log(`[CAD] Part tree: ${this.partTree.length} top-level, ${this._countTreeNodes(this.partTree)} total nodes`);
  }

  _countTreeNodes(nodes) {
    let count = 0;
    for (const n of nodes) {
      count += 1 + this._countTreeNodes(n.children);
    }
    return count;
  }

  // ── Visibility ────────────────────────────────────────────────────

  setPartVisible(name, visible) {
    // Toggle the mesh and all child meshes in the tree
    this.meshes.forEach(entry => {
      if (entry.mesh.name === name) {
        entry.mesh.visible = visible;
        entry.visible = visible;
      }
    });
    // Also hide/show all children in the tree recursively
    const setChildrenVisible = (nodes) => {
      for (const node of nodes) {
        if (node.name === name || !visible) {
          node.visible = visible;
          this.meshes.forEach(entry => {
            if (entry.mesh.name === node.name) {
              entry.mesh.visible = visible;
              entry.visible = visible;
            }
          });
        }
        setChildrenVisible(node.children);
      }
    };
    // Find the node and set all its descendants
    const findAndSet = (nodes) => {
      for (const node of nodes) {
        if (node.name === name) {
          node.visible = visible;
          // Set all descendants
          const setAll = (children) => {
            for (const child of children) {
              child.visible = visible;
              this.meshes.forEach(entry => {
                if (entry.mesh.name === child.name) {
                  entry.mesh.visible = visible;
                  entry.visible = visible;
                }
              });
              setAll(child.children);
            }
          };
          setAll(node.children);
          return true;
        }
        if (findAndSet(node.children)) return true;
      }
      return false;
    };
    findAndSet(this.partTree);
  }

  hidePart(name) {
    // Clear highlight before hiding
    this.meshes.forEach(entry => {
      if (entry.mesh.name === name) {
        entry.mesh.material.emissive.setHex(0x000000);
        entry.mesh.material.emissiveIntensity = 0;
      }
    });
    // Remove from highlighted set
    this._highlightedMeshes = this._highlightedMeshes.filter(
      m => m.name !== name
    );
    this.setPartVisible(name, false);
    this._hideStack.push(name);
    this._redoStack = [];
  }

  undoHide() {
    if (this._hideStack.length === 0) return null;
    const name = this._hideStack.pop();
    this.setPartVisible(name, true);
    // Ensure emissive is cleared on restore
    this.meshes.forEach(entry => {
      if (entry.mesh.name === name) {
        entry.mesh.material.emissive.setHex(0x000000);
        entry.mesh.material.emissiveIntensity = 0;
      }
    });
    this._redoStack.push(name);
    return name;
  }

  redoHide() {
    if (this._redoStack.length === 0) return null;
    const name = this._redoStack.pop();
    this.setPartVisible(name, false);
    this._hideStack.push(name);
    return name;
  }

  // ── Transparency ─────────────────────────────────────────────────

  setOpacity(value) {
    this.opacity = value;
    this.meshes.forEach(({ mesh }) => {
      mesh.material.opacity = value;
      mesh.material.transparent = value < 1.0;
      mesh.material.depthWrite = true;
      mesh.material.needsUpdate = true;
    });
  }

  // ── Selection ────────────────────────────────────────────────────

  handleClick(raycaster) {
    if (!this.model || this.meshes.length === 0) return null;

    // Reset previous selection (single or multi)
    if (this._highlightedMeshes.length > 0) {
      this._highlightedMeshes.forEach(m => {
        m.material.emissive.setHex(0x000000);
        m.material.emissiveIntensity = 0;
      });
      this._highlightedMeshes = [];
    }
    if (this.selectedMesh) {
      const prev = this.meshes.find(
        (m) => m.mesh === this.selectedMesh
      );
      if (prev) {
        prev.mesh.material.emissive.setHex(0x000000);
        prev.mesh.material.emissiveIntensity = 0;
      }
    }
    this._removeSelectionBox();

    const targets = this.meshes
      .filter((m) => m.visible)
      .map((m) => m.mesh);
    const hits = raycaster.intersectObjects(targets, false);

    if (hits.length === 0) {
      this.selectedMesh = null;
      if (this.onSelect) this.onSelect(null);
      return null;
    }

    const hit = hits[0];
    const mesh = hit.object;
    this.selectedMesh = mesh;
    this._highlightedMeshes = [mesh];

    // Highlight
    mesh.material.emissive.setHex(0xffaa00);
    mesh.material.emissiveIntensity = 0.4;

    // Bounding box
    this._createSelectionBox(mesh);

    // Compute info
    const worldBox = new THREE.Box3().setFromObject(mesh);
    const center = worldBox.getCenter(new THREE.Vector3());
    const bboxSize = worldBox.getSize(new THREE.Vector3());

    // Walk up to find the best name (nearest named parent)
    let name = mesh.name || '';
    if (!name || name.startsWith('mesh') || name.startsWith('Object')) {
      let parent = mesh.parent;
      while (parent && parent !== this.model) {
        if (parent.name && !parent.name.startsWith('Scene')) {
          name = parent.name;
          break;
        }
        parent = parent.parent;
      }
    }
    if (!name) name = '(unnamed)';

    const info = {
      name,
      center,       // THREE.Vector3 in scene meters
      size: bboxSize,
      point: hit.point.clone(),
    };

    if (this.onSelect) this.onSelect(info);
    return info;
  }

  _createSelectionBox(mesh) {
    this.selectionBox = new THREE.BoxHelper(mesh, 0xffaa00);
    this.selectionBox.visible = this.showBBox;
    this.scene.add(this.selectionBox);

    // Add center marker with axes and face dots
    const box = new THREE.Box3().setFromObject(mesh);
    this._createCenterMarker(box);
  }

  _createSelectionBoxFromBox3(box3) {
    // For assemblies where we already have the combined box
    const helper = new THREE.Box3Helper(box3, 0xffaa00);
    helper.visible = this.showBBox;
    this.selectionBox = helper;
    this.scene.add(helper);

    this._createCenterMarker(box3);
  }

  _createCenterMarker(box) {
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    this._centerGroup = new THREE.Group();
    this._centerGroup.visible = this.showBBox;
    this._centerGroup.renderOrder = 999;

    const minDim = Math.min(size.x, size.y, size.z);

    // Center sphere — scaled to be visible, always rendered on top
    const sphereRadius = Math.min(Math.max(minDim * 0.06, 0.008), 0.015);
    const sphereGeo = new THREE.SphereGeometry(sphereRadius, 12, 12);
    const sphereMat = new THREE.MeshBasicMaterial({
      color: 0xffffff, depthTest: false, transparent: true, opacity: 0.9,
    });
    const sphere = new THREE.Mesh(sphereGeo, sphereMat);
    sphere.renderOrder = 999;
    sphere.position.copy(center);
    this._centerGroup.add(sphere);

    // Mini axes at center — extend to ~60% of the smallest dimension
    const axisLen = Math.max(minDim * 0.6, 0.03);
    const axisInfo = [
      { dir: new THREE.Vector3(1, 0, 0), color: 0xff4444 }, // X red
      { dir: new THREE.Vector3(0, 1, 0), color: 0x44ff44 }, // Y green
      { dir: new THREE.Vector3(0, 0, 1), color: 0x4488ff }, // Z blue
    ];
    axisInfo.forEach(({ dir, color }) => {
      const arrow = new THREE.ArrowHelper(dir, center, axisLen, color, axisLen * 0.25, axisLen * 0.15);
      arrow.renderOrder = 999;
      this._centerGroup.add(arrow);
    });

    // Dots at center of each face (6 faces) — dark grey, smaller
    const dotRadius = Math.max(minDim * 0.025, 0.003);
    const dotGeo = new THREE.SphereGeometry(dotRadius, 8, 8);
    const dotMat = new THREE.MeshBasicMaterial({
      color: 0x444444, depthTest: false, transparent: true, opacity: 0.9,
    });
    const halfSize = size.clone().multiplyScalar(0.5);
    const faceOffsets = [
      new THREE.Vector3(halfSize.x, 0, 0),   // +X face
      new THREE.Vector3(-halfSize.x, 0, 0),  // -X face
      new THREE.Vector3(0, halfSize.y, 0),   // +Y face
      new THREE.Vector3(0, -halfSize.y, 0),  // -Y face
      new THREE.Vector3(0, 0, halfSize.z),   // +Z face
      new THREE.Vector3(0, 0, -halfSize.z),  // -Z face
    ];
    faceOffsets.forEach(offset => {
      const dot = new THREE.Mesh(dotGeo, dotMat);
      dot.renderOrder = 999;
      dot.position.copy(center).add(offset);
      this._centerGroup.add(dot);
    });

    this.scene.add(this._centerGroup);
  }

  _removeSelectionBox() {
    if (this.selectionBox) {
      this.scene.remove(this.selectionBox);
      if (this.selectionBox.dispose) this.selectionBox.dispose();
      this.selectionBox = null;
    }
    if (this._centerGroup) {
      this.scene.remove(this._centerGroup);
      this._centerGroup = null;
    }
  }

  rotateYaw90() {
    if (!this.model) return;
    this._yawSteps = (this._yawSteps + 1) % 4;
    this._applyOrientation();
    this._removeSelectionBox();
  }

  rotateX90() {
    if (!this.model) return;
    this._xSteps = (this._xSteps + 1) % 4;
    this._applyOrientation();
    this._removeSelectionBox();
  }

  _applyOrientation() {
    if (!this.model) return;
    const xAngle = (this._xSteps * Math.PI) / 2;
    const zAngle = (this._yawSteps * Math.PI) / 2;
    const qX = new THREE.Quaternion();
    qX.setFromAxisAngle(new THREE.Vector3(1, 0, 0), xAngle);
    const qZ = new THREE.Quaternion();
    qZ.setFromAxisAngle(new THREE.Vector3(0, 0, 1), zAngle);
    const combined = new THREE.Quaternion();
    combined.multiplyQuaternions(qZ, qX);
    this.model.quaternion.copy(combined);
    console.log(`[CAD] X=${this._xSteps * 90}° Yaw=${this._yawSteps * 90}°`);
  }

  setShowBBox(show) {
    this.showBBox = show;
    if (this.selectionBox) this.selectionBox.visible = show;
    if (this._centerGroup) this._centerGroup.visible = show;
  }

  // ── Cleanup ──────────────────────────────────────────────────────

  unload() {
    this._removeSelectionBox();
    this.selectedMesh = null;

    if (this.model) {
      this.model.traverse((obj) => {
        if (obj.isMesh) {
          obj.geometry.dispose();
          if (obj.material) {
            if (obj.material.map) obj.material.map.dispose();
            obj.material.dispose();
          }
        }
      });
      this.modelParent.remove(this.model);
      this.model = null;
    }
    this.meshes = [];
  }

  // ── Internal ─────────────────────────────────────────────────────

  _setStatus(text) {
    if (this.onStatusChange) this.onStatusChange(text);
  }
}
